"""Generate a batch of DOI, byline, and explicit primary-abstract evidence checks."""

import argparse
from collections import Counter, defaultdict
from pathlib import Path
import re

from apply_followup import PRIMARY, REVIEWED
from collect_paper_sources import match_title
from followup_http import cache_rows, plain_markup
from primary_methods import extract
from sync import ROOT, load, orcid_key, save, words


def exact_name(left, right):
    a, b = words(left), words(right)
    if not a or not b:
        return False
    if a == b:
        return len(a) >= 2
    particles = {"van", "von", "de", "da", "del", "der", "di", "den", "du"}
    middle_a, middle_b = ([part[0] for part in parts[1:-1] if part not in particles] for parts in (a, b))
    return (min(len(a), len(b)) >= 2 and a[-1] == b[-1] and len(a[0]) > 1 and a[0] == b[0]
            and all(x == y for x, y in zip(middle_a, middle_b)))


def record_names(work):
    return [" ".join(filter(None, (row.get("given"), row.get("family") or row.get("name"))))
            for row in work.get("author", [])]


def author_state(person, names, work, roster_names, school):
    orcid = orcid_key(person["orcid"])
    if orcid and sum(orcid_key(row.get("ORCID")) == orcid for row in work.get("author", [])) == 1:
        return "orcid_match"
    indexes = [i for i, name in enumerate(names) if exact_name(name, person["name"])]
    if len(indexes) != 1:
        return "byline_unconfirmed"
    if roster_names[tuple(words(person["name"]))] != 1:
        affiliation = work.get("author", [])[indexes[0]].get("affiliation", []) if work.get("author") else []
        if not any(school["name"].casefold() in (row.get("name") or "").casefold() for row in affiliation):
            return "same_name_needs_affiliation"
    return "byline_match"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("registry", type=Path)
    parser.add_argument("sources", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--date", required=True)
    parser.add_argument("--incremental", action="store_true")
    parser.add_argument("--alternate-plan", type=Path)
    args = parser.parse_args()
    root = ROOT / "data"
    cohorts = load(root / "followup/cohorts.json")
    method_review = cohorts["method_review"]
    paper_queue = cohorts["paper_queue"]
    if args.alternate_plan:
        alternate = load(args.alternate_plan)
        method_review, paper_queue = alternate["method_review"], alternate["paper_queue"]
    prior = [load(path) for path in sorted((root / "followup").glob("batch-*.json"))
             if path.resolve() != args.output.resolve()]
    manual = {row["paper_id"] for batch in prior for row in batch.get("evidence", []) if row["level"] == REVIEWED}
    manual.update(row["paper_id"] for batch in prior for row in batch.get("papers", [])
                  if row["state"].startswith("manual_"))
    prior_marks = {(row["person_id"], row["paper_id"], row["tag"]): row for batch in prior
                   for row in batch.get("evidence", []) if row["level"] == PRIMARY}
    prior_outcomes = {row["paper_id"]: row["state"] for batch in prior for row in batch.get("papers", [])}
    works, faculty, schools = (load(root / f"{name}.json") for name in ("papers", "faculty", "schools"))
    roster_names = Counter(tuple(words(person["name"])) for person in faculty.values())
    registry, sources = cache_rows(args.registry), cache_rows(args.sources)
    people_by_work = defaultdict(list)
    for pid, ids in method_review.items():
        for wid in ids:
            people_by_work[wid].append(pid)

    papers, byline, evidence = [], [], []
    for wid in paper_queue:
        if wid in manual:
            continue
        paper = works[wid]
        doi = paper["doi"]
        if doi not in registry and doi not in sources:
            continue
        record = registry.get(doi, {})
        work = record.get("work", {})
        page = sources.get(doi, {})
        names = record_names(work) or page.get("authors", [])
        doi_matches = work.get("DOI", "").lower() == doi
        title_matches = any(match_title(paper["title"], plain_markup(title)) for title in work.get("title", []))
        text = plain_markup(work.get("abstract", "")) if doi_matches and title_matches else ""
        source, location = record.get("url"), "Publisher-deposited abstract via Crossref"
        if len(text) < 85 and page.get("abstract") and doi_matches:
            text, source = page["abstract"], page["url"]
            location = ("Author manuscript abstract" if page["kind"] == "public_manuscript"
                        else "Publisher page abstract")
        if not text:
            outcome = ("metadata_mismatch" if work and not (doi_matches and title_matches) else
                       "registry_only" if work else "source_unavailable")
            marks = []
        else:
            marks = extract(text)
            outcome = "primary_methods_found" if marks else "primary_abstract_no_explicit_method"
        papers.append({"paper_id": wid, "source": source or f"https://doi.org/{doi}", "state": outcome})
        for pid in people_by_work[wid]:
            person = faculty[pid]
            state = author_state(person, names, work, roster_names, schools[person["school"]])
            byline.append({"person_id": pid, "paper_id": wid, "state": state})
            if state not in {"byline_match", "orcid_match"}:
                continue
            for item in marks:
                evidence.append({"person_id": pid, "paper_id": wid, "level": PRIMARY,
                                 "source": source, "locator": f"{location}, sentence {item['sentence']}", **item})

    if args.incremental:
        papers = [row for row in papers if prior_outcomes.get(row["paper_id"]) != row["state"]]
        evidence = [row for row in evidence if (row["person_id"], row["paper_id"], row["tag"]) not in prior_marks]
        additions = {row["paper_id"] for row in papers + evidence}
        byline = [row for row in byline if row["paper_id"] in additions]
    save(args.output, {"checked_at": args.date, "summary": "DOI and authorship checks with explicit primary-abstract methods.",
                       "papers": papers, "author_checks": byline, "evidence": evidence})
    print(Counter(paper["state"] for paper in papers))
    print(Counter(row["state"] for row in byline))
    print(f"{len(evidence)} annotated claims for {len({row['person_id'] for row in evidence})} faculty.")


if __name__ == "__main__":
    main()
