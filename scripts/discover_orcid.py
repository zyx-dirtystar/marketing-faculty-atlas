"""Find recent papers for empty profiles using the roster's exact ORCID."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from sync import ROOT, load, save

ORCID = re.compile(r"^(?:https?://orcid\.org/)?(\d{4}-\d{4}-\d{4}-\d{3}[\dX])$", re.I)
ARTICLE_TYPES = {"article", "preprint", "working-paper"}


def look_up(item):
    pid, value = item
    match = ORCID.fullmatch((value or "").strip().rstrip("/"))
    if not match:
        return pid, {"state": "invalid_orcid", "papers": []}
    orcid = "https://orcid.org/" + match[1].upper()
    params = {
        "filter": "author.orcid:" + orcid + ",has_doi:true",
        "select": "id,doi,title,authorships,abstract_inverted_index,is_retracted,publication_year,type,primary_location",
        "per-page": 18,
        "sort": "publication_date:desc",
    }
    if key := os.environ.get("OPENALEX_API_KEY"):
        params["api_key"] = key
    request = Request("https://api.openalex.org/works?" + urlencode(params),
                      headers={"User-Agent": "MarketingFacultyAtlas/1.0"})
    for attempt in range(3):
        try:
            with urlopen(request, timeout=30) as response:
                rows = json.load(response)["results"]
            selected = [
                row for row in rows if row["type"] in ARTICLE_TYPES and not row.get("is_retracted")
                and any(entry.get("author", {}).get("orcid") == orcid for entry in row["authorships"])]
            return pid, {"state": "checked", "orcid": orcid, "papers": selected}
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            if isinstance(exc, HTTPError) and exc.code in {400, 401, 403, 404}:
                break
            time.sleep(2 ** attempt)
    return pid, {"state": "lookup_failed", "orcid": orcid, "papers": []}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    faculty = load(ROOT / "data/faculty.json")
    empty = [(pid, row["orcid"]) for pid, row in faculty.items()
             if not row["upstream_paper_count"] and row["orcid"]]
    old = load(args.output) if args.output.exists() else {}
    pending = [item for item in empty if old.get(item[0], {}).get("state") != "checked"]
    with ThreadPoolExecutor(max_workers=5) as pool:
        old.update(pool.map(look_up, pending))
    save(args.output, old)
    print(f"{len(empty)} ORCIDs; {sum(bool(row['papers']) for row in old.values())} yielded candidate works.")


if __name__ == "__main__":
    main()
