"""Record individually checked full-text sources and anchored methods evidence."""

import argparse
from collections import Counter, defaultdict
from pathlib import Path
import re

from apply_followup import FULLTEXT, PRIMARY
from collect_paper_sources import match_title
from followup_http import cache_rows, plain_markup
from make_method_batch import author_state, record_names
from primary_methods import extract
from sync import ROOT, load, save, words


def normalize_section(value):
    value = re.sub(r"([A-Za-z]{3,})-\s+([a-z]{2,})", r"\1\2", value)
    return " ".join(value.replace("\u00ad", "").split())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("registry", type=Path)
    parser.add_argument("fulltext", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    source = ROOT / "data"
    plan = load(source / "followup/deep-review-plan.json")
    papers, people, schools = (load(source / f"{key}.json") for key in ("papers", "faculty", "schools"))
    roster = Counter(tuple(words(person["name"])) for person in people.values())
    registry, fulltexts = cache_rows(args.registry), cache_rows(args.fulltext)
    linked = defaultdict(list)
    for pid, works in plan["method_review"].items():
        for wid in works:
            linked[wid].append(pid)
    batch = {"checked_at": args.date,
             "summary": "Public full-text, author manuscript and DOI review of known titles for the remaining method cohort.",
             "fulltext_checks": [], "papers": [], "author_checks": [], "evidence": []}
    for wid, pids in linked.items():
        paper = papers[wid]
        doi = paper["doi"]
        if not doi:
            continue
        record = registry.get(doi, {})
        work = record.get("work", {})
        text = fulltexts.get(doi, {})
        canonical = f"https://doi.org/{doi}"
        if record or text:
            batch["papers"].append({"paper_id": wid, "state": "deeper_source_check",
                                    "source": record.get("url") or text.get("source") or canonical})
        if text:
            batch["fulltext_checks"].append({"paper_id": wid, "state": text["status"], "source": text["source"],
                                            "attempts": text.get("attempts", [])})
        doi_matches = work.get("DOI", "").lower() == doi
        title_matches = any(match_title(paper["title"], plain_markup(t)) for t in work.get("title", []))
        if not (doi_matches and title_matches):
            continue
        byline = record_names(work)
        marks = {}
        for section in text.get("sections", []):
            for hit in extract(normalize_section(section["text"])):
                entry = {**hit, "level": FULLTEXT, "source": text["source"],
                         "locator": section["locator"] + f", sentence {hit['sentence']}",
                         "note": "The methods text reports " + hit["technique"][0].lower() + hit["technique"][1:] + "."}
                before = marks.get(hit["tag"])
                if not before or (before.get("derived_from") and not hit.get("derived_from")):
                    marks[hit["tag"]] = entry
        deposition = plain_markup(work.get("abstract"))
        for hit in extract(deposition):
            marks.setdefault(hit["tag"], {**hit, "level": PRIMARY, "source": record["url"],
                                          "locator": f"Publisher-deposited abstract via Crossref, sentence {hit['sentence']}"})
        for pid in pids:
            person = people[pid]
            identity = author_state(person, byline, work, roster, schools[person["school"]])
            batch["author_checks"].append({"person_id": pid, "paper_id": wid, "state": identity})
            if identity in {"byline_match", "orcid_match"}:
                batch["evidence"].extend({"person_id": pid, "paper_id": wid, **row} for row in marks.values())
    save(args.output, batch)
    print(Counter(row["state"] for row in batch["fulltext_checks"]))
    print(f"{len(batch['evidence'])} linked claims for {len({r['person_id'] for r in batch['evidence']})} faculty.")


if __name__ == "__main__":
    main()
