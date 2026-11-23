"""Cache DOI-matched OpenAlex metadata locally. Publication uses derived labels only."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def fetch(dois):
    params = {
        "filter": "doi:" + "|".join(dois),
        "select": "id,doi,title,authorships,abstract_inverted_index,is_retracted",
        "per-page": len(dois),
    }
    if key := os.environ.get("OPENALEX_API_KEY"):
        params["api_key"] = key
    request = Request("https://api.openalex.org/works?" + urlencode(params),
                      headers={"User-Agent": "MarketingFacultyAtlas/1.0"})
    for attempt in range(4):
        try:
            with urlopen(request, timeout=30) as response:
                rows = json.load(response)["results"]
            found = {row["doi"].removeprefix("https://doi.org/").lower(): row
                     for row in rows if row.get("doi")}
            return {doi: found.get(doi) for doi in dois}
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            if isinstance(exc, HTTPError) and exc.code in {400, 401, 403, 404}:
                break
            if attempt < 3:
                time.sleep(2 ** attempt)
    return {}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("upstream", type=Path)
    parser.add_argument("cache", type=Path)
    args = parser.parse_args()
    site = args.upstream / "site"
    index = json.loads((site / "data.js").read_text(encoding="utf-8").strip()
                       .removeprefix("window.EF = ").removesuffix(";"))
    rows = (dict(zip(index["cols"], values)) for values in index["people"])
    ids = [row["id"] for row in rows
           if any(index["pfields"][i].split(":")[0] == "Marketing"
                  for i in row["pfield"])]
    dois = set()
    for person_id in ids:
        path = site / "pubs" / f"{person_id}.json"
        if path.exists():
            dois.update(paper["doi"].lower() for paper in json.loads(path.read_text(encoding="utf-8"))
                        if paper.get("doi"))
    args.cache.parent.mkdir(parents=True, exist_ok=True)
    cached = {}
    if args.cache.exists():
        for line in args.cache.read_text(encoding="utf-8").splitlines():
            cached.update(json.loads(line))
    remaining = sorted(dois - cached.keys())
    batches = [remaining[i:i + 50] for i in range(0, len(remaining), 50)]
    print(f"{len(dois)} DOIs, {len(remaining)} to fetch in {len(batches)} batches.", flush=True)
    with args.cache.open("a", encoding="utf-8") as output, ThreadPoolExecutor(max_workers=6) as pool:
        for i, result in enumerate(pool.map(fetch, batches), 1):
            if result:
                print(json.dumps(result, ensure_ascii=False), file=output, flush=True)
                cached.update(result)
            if i % 30 == 0 or i == len(batches):
                print(f"{i}/{len(batches)} batches, {len(cached)} DOI lookups saved.", flush=True)
    abstracts = sum(bool((row or {}).get("abstract_inverted_index")) for row in cached.values())
    print(f"{len(cached)} DOI lookups and {abstracts} abstracts.")
    if dois - cached.keys():
        sys.exit("Some DOI lookups remain retryable.")


if __name__ == "__main__":
    main()
