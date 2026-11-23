"""Try exact title searches for known papers that lack a DOI in the roster."""

import argparse
from collections import defaultdict
import json
from pathlib import Path
from urllib.parse import urlencode

from followup_http import Network, collect, plain_markup
from make_method_batch import exact_name, record_names
from sync import ROOT, load, title_key


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    plan = load(ROOT / "data/followup/deep-review-plan.json")
    papers = load(ROOT / "data/papers.json")
    faculty = load(ROOT / "data/faculty.json")
    missing = [wid for wid in plan["paper_queue"] if not papers[wid]["doi"]]
    authors = defaultdict(list)
    for pid, keys in plan["method_review"].items():
        for wid in keys:
            authors[wid].append(faculty[pid]["name"])
    network = Network()

    def resolve(wid):
        paper = papers[wid]
        search = "https://api.crossref.org/works?" + urlencode(
            {"query.title": paper["title"][:350], "rows": 5,
             "select": "DOI,title,author,published,container-title,type,URL"})
        response, body = network.get(search, "application/json")
        candidates = {}
        for row in json.loads(body)["message"]["items"] if body else []:
            if not any(title_key(plain_markup(t)) == title_key(paper["title"]) for t in row.get("title", [])):
                continue
            if not any(exact_name(name, byline) for name in authors[wid] for byline in record_names(row)):
                continue
            candidates[row["DOI"].lower()] = row
        return {"status": "exact_title_byline" if len(candidates) == 1 else
                "ambiguous" if candidates else "unmatched" if body else response["status"],
                "source": search, "matches": list(candidates.values())}

    collect(missing, resolve, args.output, workers=6)


if __name__ == "__main__":
    main()
