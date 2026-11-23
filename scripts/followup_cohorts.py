"""Create the fixed faculty cohorts and paper review queue from the first release."""

import argparse
from collections import defaultdict
from pathlib import Path

from sync import ROOT, load, save

BASELINE = "ca878e6"


def method_tags(taxonomy):
    return set().union(*(taxonomy[key] for key in ("method", "design", "identification")),
                       ("causal", "predictive", "counterfactual", "descriptive"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=ROOT / "dist/data.json")
    parser.add_argument("--output", type=Path, default=ROOT / "data/followup/cohorts.json")
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("The fixed cohorts already exist.")
    catalog = load(args.catalog)
    methods = method_tags(catalog["taxonomy"])
    faculty = [row for row in catalog["people"] if row["status"] == "abstract_signal"
               and methods.intersection(row["counts"]["abstract_signal"])]
    missing = sorted(row["id"] for row in catalog["people"] if row["status"] == "no_papers")
    candidates = defaultdict(set)
    for mark in load(ROOT / "data/evidence.json"):
        if mark["level"] == "abstract_signal" and mark["tag"] in methods:
            candidates[mark["paper_id"]].add(mark["tag"])
    links = defaultdict(list)
    ids = {row["id"] for row in faculty}
    for row in load(ROOT / "data/authorships.json"):
        if row["person_id"] in ids and row["identity"] != "review_needed" and row["paper_id"] in candidates:
            links[row["person_id"]].append(row["paper_id"])
    assert len(ids) == 777 and len(missing) == 469 and set(links) == ids
    works = {paper for papers in links.values() for paper in papers}
    save(args.output, {"baseline": BASELINE, "method_review": {k: sorted(links[k]) for k in sorted(links)},
                       "paper_queue": {key: sorted(candidates[key]) for key in sorted(works)},
                       "publication_search": missing})
    print(f"{len(ids)} method reviews and {len(missing)} searches. {len(works)} distinct papers in the queue.")


if __name__ == "__main__":
    main()
