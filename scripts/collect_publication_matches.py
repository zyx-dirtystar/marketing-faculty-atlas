"""Resolve DOI and citation leads from each faculty member's publication sources."""

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlencode

from followup_http import Network, cache_rows, collect
from sync import ROOT, load, save, words


def citation_priority(snippet, name):
    tokens = words(snippet)
    family = words(name)[-1:]
    year = bool(re.search(r"\b(?:19|20)\d{2}\b", snippet))
    author = bool(family and family[0] in tokens)
    journal = bool(re.search(r"journal|marketing science|management science|vol\.|pp\.|doi", snippet, re.I))
    return 4 * author + 2 * journal + year


def pipeline(faculty_results, faculty):
    dois, citations = defaultdict(set), {}
    for pid, row in faculty_results.items():
        for doi in row["dois"]:
            dois[doi].add(pid)
        stack = {}
        for source in row["sources"]:
            for snippet in source["citations"]:
                priority = citation_priority(snippet, faculty[pid]["name"])
                if priority >= 3:
                    stack.setdefault(snippet, (priority, source["url"]))
        ordered = sorted(stack.items(), key=lambda item: (-item[1][0], item[0]))
        for snippet, (_, url) in ordered[:5]:
            key = pid + ":" + hashlib.sha256(snippet.encode()).hexdigest()[:14]
            citations[key] = {"person_id": pid, "snippet": snippet, "url": url}
    return sorted(dois, key=lambda doi: (len(dois[doi]) > 3, doi)), citations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("faculty_sources", type=Path)
    parser.add_argument("doi_cache", type=Path)
    parser.add_argument("citation_cache", type=Path)
    parser.add_argument("--review-registry", type=Path)
    parser.add_argument("--retry", action="store_true")
    args = parser.parse_args()
    persons = load(ROOT / "data/faculty.json")
    dois, citations = pipeline(cache_rows(args.faculty_sources), persons)
    registry = cache_rows(args.review_registry) if args.review_registry else {}
    network = Network()

    def read_citation(key):
        row = citations[key]
        person = persons[row["person_id"]]
        params = {"query.bibliographic": row["snippet"][:300], "query.author": person["name"],
                  "rows": 4, "select": "DOI,title,author,published,container-title,type,URL"}
        outcome, body = network.get("https://api.crossref.org/works?" + urlencode(params), "application/json")
        records = json.loads(body).get("message", {}).get("items", []) if body else []
        return {**outcome, **row, "candidates": records}

    collect([doi for doi in dois if registry.get(doi, {}).get("status") != "read"],
            network.crossref, args.doi_cache, workers=9, retry=args.retry)
    collect(sorted(citations), read_citation, args.citation_cache, workers=9, retry=args.retry)


if __name__ == "__main__":
    main()
