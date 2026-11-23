"""Resolve citations visible in official profile excerpts and verified CVs."""

import argparse
import json
from pathlib import Path
import re

from collect_faculty_sources import find_dois, name_present, title_candidates
from followup_http import cache_rows
from make_publication_batch import owner_source, stable_url
from sync import ROOT, load

PUBLICATION_CONTEXT = re.compile(
    r"\b(?:publications?|research outputs?|journal articles?|working papers?|peer.reviewed|"
    r"selected works|DOI|Journal of|forthcoming|in press)\b|发表论文|研究成果|期刊论文", re.I)
CITATION_SIGNAL = re.compile(
    r"\b(?:19|20)\d{2}\b|\b(?:in press|forthcoming|journal|marketing science|management science)\b", re.I)
IRRELEVANT = re.compile(
    r"\b(?:enquire|click here|awarded|received (?:his|her|the)|copyright|rights reserved|"
    r"weather forecast|admissions|application deadline)\b", re.I)


def visible_citations(excerpt):
    lines = [" ".join(line.split()).strip("• ") for line in excerpt.splitlines()]
    hits = []
    for i, line in enumerate(lines):
        if not PUBLICATION_CONTEXT.search(line):
            continue
        if 40 <= len(line) <= 340:
            hits.append(line)
        for adjacent in lines[i + 1:i + 3]:
            if 25 <= len(adjacent) <= 140:
                hits.append(line + " " + adjacent)
    return [line for line in title_candidates(lines + hits)
            if CITATION_SIGNAL.search(line) and not IRRELEVANT.search(line)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("search", type=Path, nargs="+")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verified-sources", type=Path)
    parser.add_argument("--aliases", type=Path)
    parser.add_argument("--previous", type=Path)
    args = parser.parse_args()
    people = load(ROOT / "data/faculty.json")
    group = load(ROOT / "data/followup/deep-review-plan.json")["publication_search"]
    confirmed = {row["person_id"] for row in load(args.previous)["publications"]} if args.previous else set()
    sources = load(args.verified_sources) if args.verified_sources else {}
    aliases = load(args.aliases) if args.aliases else {}
    searches = [load(path) for path in args.search]
    with args.output.open("w", encoding="utf-8") as stream:
        for pid in group:
            if pid in confirmed:
                continue
            person = people[pid]
            extra = sources.get(pid, [])
            names = [person["name"], *aliases.get(pid, [])]
            rows, dois = {}, {}
            for results in searches:
                for hit in results.get(pid, []):
                    url = stable_url(hit["url"])
                    text = hit["evidence"]
                    if not owner_source(person, url, extra) or not PUBLICATION_CONTEXT.search(text):
                        continue
                    if not any(name_present(name, hit["title"] + " " + text[:3800]) for name in names):
                        continue
                    snippets = visible_citations(text)
                    item = rows.setdefault(url, {"url": url, "role": "indexed_profile_excerpt",
                                                "status": "identity_checked", "citations": []})
                    item["citations"] = sorted(set(item["citations"] + snippets))
                    for doi in find_dois(text):
                        dois.setdefault(doi, []).append(url)
            result = {"status": "checked" if rows else "no_source",
                      "sources": list(rows.values()), "dois": dois}
            print(json.dumps([pid, result], ensure_ascii=False), file=stream)


if __name__ == "__main__":
    main()
