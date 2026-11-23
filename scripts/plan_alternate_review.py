"""Select alternate papers for remaining faculty, using indexed text only for selection."""

import argparse
from collections import defaultdict
from pathlib import Path

from apply_followup import PRIMARY, REVIEWED
from followup_cohorts import method_tags
from primary_methods import extract
from sync import ROOT, abstract_text, load, read_cache, save


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("indexed_abstracts", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    data = ROOT / "data"
    followup = data / "followup"
    cohort = load(followup / "cohorts.json")
    people = set(cohort["method_review"])
    base_queue = cohort["paper_queue"]
    methods = method_tags(load(data / "taxonomy.json"))
    for file in followup.glob("batch-*.json"):
        people.difference_update(row["person_id"] for row in load(file).get("evidence", [])
                                 if row["level"] in (PRIMARY, REVIEWED) and row["tag"] in methods)
    cache = read_cache(args.indexed_abstracts)
    papers = load(data / "papers.json")
    candidates = defaultdict(list)
    tags = {}
    for row in load(data / "authorships.json"):
        pid, wid = row["person_id"], row["paper_id"]
        if pid not in people or wid in base_queue or row["identity"] == "review_needed":
            continue
        paper = papers[wid]
        if not paper["doi"] or paper["retracted"]:
            continue
        if wid not in tags:
            evidence = extract(abstract_text(cache.get(paper["doi"]) or {}))
            tags[wid] = sorted({item["tag"] for item in evidence if item["tag"] in methods})
        if tags[wid]:
            candidates[pid].append(wid)
    chosen = {pid: sorted(set(ids), key=lambda w: (-len(tags[w]), -(papers[w]["year"] or 0), w))[:3]
              for pid, ids in sorted(candidates.items())}
    used = {wid for ids in chosen.values() for wid in ids}
    save(args.output, {"method_review": chosen, "paper_queue": {w: tags[w] for w in sorted(used)}})
    print(f"{len(people)} unresolved faculty; selected {len(used)} alternate papers for {len(chosen)} faculty.")


if __name__ == "__main__":
    main()
