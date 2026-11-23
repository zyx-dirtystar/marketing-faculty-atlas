"""Check replacement faculty/CV links and additional institutional research outputs."""

import argparse
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

from collect_faculty_sources import CV, FacultySources, allowed, find_dois, name_present
from followup_http import collect
from sync import ROOT, load, title_key

PORTAL = re.compile(r"(?:^|[./])(?:research|pure|scholars|experts|repository|eprints|scholarworks|"
                    r"discovery|researchportal|dipot|difusion|digitalcommons|faculty|academic)(?:[./-]|$)", re.I)
UNSUITABLE = {"researchgate.net", "scholar.google.com", "academia.edu"}


def sources_from_search(person, search_hits, official_url):
    options = {}
    fullname = title_key(person["name"])
    root_h = (urlsplit(official_url).hostname or "").removeprefix("www.")
    for hit in search_hits:
        url, title = hit["url"], hit["title"]
        if not allowed(url):
            continue
        parsed = urlsplit(url)
        host = parsed.hostname.removeprefix("www.")
        if host in UNSUITABLE or re.search(r"(?:journals*of.*toc|scholarly articles, journals|search results|"
                                          r"conference program|call for papers)", title, re.I):
            continue
        self_title = name_present(person["name"], title)
        self_url = fullname and fullname in title_key(host + parsed.path)
        portal = PORTAL.search(host + parsed.path)
        official = root_h == host or ".edu" in host or ".ac." in host or bool(portal)
        if re.search(r"\.pdf(?:[?#]|$)", url, re.I) and (CV.search(title) or CV.search(parsed.path)
                                                        or "curriculum vitae" in hit["evidence"].lower()):
            role, priority = "cv", 9 if official else 7
        elif find_dois(url) or re.search(r"/(?:publications|outputs|facpub|article|articles|works)/[^/?#]+", url, re.I):
            if not (official or "doi.org" in host or portal or "wiley" in host or "informs" in host
                    or "sagepub" in host or "sciencedirect" in host or "springer" in host):
                continue
            role, priority = "publication_record", 6 if official else 4
        elif self_title or self_url:
            role, priority = ("profile" if official else "home"), 8 if official else 6
        else:
            continue
        options[url] = (priority, role)
    return [(role, url) for url, (_, role) in sorted(options.items(), key=lambda row: -row[1][0])[:6]]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("search_hits", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--deps", type=Path)
    parser.add_argument("--placement", type=Path)
    parser.add_argument("--aliases-output", type=Path)
    parser.add_argument("--linked-only", action="store_true")
    parser.add_argument("--cohort", choices=("method_review", "publication_search"), required=True)
    args = parser.parse_args()
    if args.deps:
        sys.path.insert(0, str(args.deps.resolve()))
    from bs4 import BeautifulSoup

    search = load(args.search_hits)
    faculty = load(ROOT / "data/faculty.json")
    plan = load(ROOT / "data/followup/deep-review-plan.json")
    group = list(plan[args.cohort])
    sources = {pid: sources_from_search(faculty[pid], search.get(pid, []),
                                        faculty[pid]["links"].get("profile_url", "")) for pid in group}
    if args.placement:
        from sync import save

        placement = {row["id"]: row for row in load(args.placement)["people"]}
        aliases = {}
        for pid in group:
            match = faculty[pid].get("placement", {})
            candidates = match.get("candidates", [])
            if match.get("state") != "shared_profile_url" or len(candidates) != 1:
                continue
            row = placement.get(candidates[0]["id"], {})
            if not row:
                continue
            names = sorted({name for name in (row["name"], *row.get("aliases", []))
                            if name and name != faculty[pid]["name"]})
            aliases[pid] = names
            faculty[pid]["publication_aliases"] = names
            sources[pid] = [("cv", row.get("cv_url")), ("home", row.get("homepage")), *sources[pid]]
        if args.aliases_output:
            save(args.aliases_output, aliases)
        if args.linked_only:
            group = list(aliases)
    print(f"{sum(bool(sources[pid]) for pid in group)}/{len(group)} faculty have additional source links.", flush=True)
    collect(group, FacultySources(faculty, BeautifulSoup, sources, deep=True), args.output, workers=24)


if __name__ == "__main__":
    main()
