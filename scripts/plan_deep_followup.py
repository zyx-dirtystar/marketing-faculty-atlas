"""Pin the remaining faculty and enumerate their known papers for deeper follow-up."""

import argparse
from collections import defaultdict
from pathlib import Path

from sync import ROOT, load, save


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    current = load(ROOT / "dist/download/followup.json")
    methods = set(row["person_id"] for row in current if row.get("cohort") == "method_review"
                  and row["state"] == "sources_checked")
    publications = sorted(row["person_id"] for row in current if row.get("cohort") == "publication_search"
                          and row["state"] != "papers_found")
    works = load(ROOT / "data/papers.json")
    candidates = defaultdict(list)
    for row in load(ROOT / "data/authorships.json"):
        pid, wid = row["person_id"], row["paper_id"]
        if pid in methods and row["identity"] != "review_needed" and not works[wid]["retracted"]:
            candidates[pid].append(wid)
    if (len(methods), len(publications)) != (84, 270) or set(candidates) != methods:
        raise ValueError("Use the b7c7b9e baseline to generate this round's fixed cohorts.")
    save(args.output, {"baseline": "b7c7b9e", "method_review": {pid: sorted(candidates[pid]) for pid in sorted(methods)},
                       "paper_queue": {wid: [] for wid in sorted({w for ids in candidates.values() for w in ids})},
                       "publication_search": publications})
    print(f"{len(methods)} method reviews; {len(publications)} publication searches; "
          f"{len({w for ids in candidates.values() for w in ids})} known papers.")


if __name__ == "__main__":
    main()
