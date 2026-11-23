"""Publish confirmed publication links and source-search outcomes from local caches."""

import argparse
from collections import Counter, defaultdict
from pathlib import Path
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from apply_followup import PRIMARY
from followup_http import cache_rows, plain_markup
from make_method_batch import exact_name, record_names
from primary_methods import extract
from sync import ROOT, href, load, save, title_key

TYPES = {"journal-article", "posted-content", "proceedings-article"}


def stable_url(url):
    parsed = urlsplit(href(url))
    if not parsed.netloc:
        return ""
    query = [(field, value) for field, value in parse_qsl(parsed.query, keep_blank_values=True)
             if not re.search(r"token|signature|password|secret|^x-amz-|^key$|^auth$", field, re.I)]
    return urlunsplit(parsed._replace(query=urlencode(query), fragment=""))


def publication(registry, person, doi, source, method, citation=None):
    type_ = registry.get("type")
    if type_ not in TYPES or not registry.get("title") or registry.get("DOI", "").lower() != doi:
        return None
    names = record_names(registry)
    if sum(exact_name(name, person["name"]) for name in names) != 1:
        return None
    title = plain_markup(registry["title"][0])
    if citation and (len(title_key(title)) < 24 or title_key(title) not in title_key(citation)):
        return None
    date_parts = (registry.get("published") or {}).get("date-parts", [[None]])
    return {"person_id": person["id"], "doi": doi, "title": title, "authors": names,
            "year": next(iter(date_parts[0]), None),
            "venue": next(iter(registry.get("container-title", [])), None),
            "status": "wp" if type_ == "posted-content" else "pub",
            "discovery_method": method, "listing_url": stable_url(source),
            "verification_url": "https://doi.org/" + doi}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("faculty_sources", type=Path)
    parser.add_argument("registries", type=Path, nargs="+")
    parser.add_argument("--citations", type=Path)
    parser.add_argument("--affiliations", type=Path)
    parser.add_argument("--manual", type=Path)
    parser.add_argument("--date", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sources = cache_rows(args.faculty_sources)
    registry = {}
    for file in args.registries:
        registry.update(cache_rows(file))
    citations_by_person = defaultdict(list)
    for row in cache_rows(args.citations).values() if args.citations else []:
        citations_by_person[row["person_id"]].append(row)
    affiliations = cache_rows(args.affiliations) if args.affiliations else {}
    manual = load(args.manual) if args.manual else {}
    faculty = load(ROOT / "data/faculty.json")
    baseline = load(ROOT / "data/papers.json")
    cohort = load(ROOT / "data/followup/cohorts.json")["publication_search"]
    works, evidence, checks = [], [], []
    for pid in cohort:
        if pid not in sources and pid not in manual:
            continue
        local = sources.get(pid, {"sources": [], "dois": {}})
        author = faculty[pid]
        matched = {}

        def add(row, abstract, evidence_url):
            if (not row or not row["listing_url"] or row["doi"] in matched or
                    baseline.get("doi:" + row["doi"], {}).get("retracted")):
                return
            matched[row["doi"]] = row
            for mark in extract(abstract):
                evidence.append({"person_id": pid, "paper_id": "doi:" + row["doi"],
                                 "level": PRIMARY, "source": evidence_url,
                                 "locator": f"Publisher-deposited abstract via Crossref, sentence {mark['sentence']}",
                                 **mark})

        for doi, urls in sorted({**local["dois"], **manual.get(pid, {}).get("dois", {})}.items()):
            metadata = registry.get(doi, {})
            record = metadata.get("work", {})
            row = publication(record, author, doi, urls[0], "faculty_doi")
            add(row, plain_markup(record.get("abstract")), metadata.get("url", ""))
        for citation in citations_by_person[pid]:
            matches = {}
            for candidate in citation.get("candidates", []):
                doi = candidate.get("DOI", "").lower()
                row = publication(candidate, author, doi, citation["url"], "faculty_citation", citation["snippet"])
                if row:
                    matches[doi] = row
            if len(matches) == 1:
                add(next(iter(matches.values())), "", "")
        index_match = affiliations.get(pid, {})
        for paper in index_match.get("papers", []):
            doi = paper["doi"].removeprefix("https://doi.org/").lower()
            location = (paper.get("primary_location") or {}).get("source") or {}
            row = {"person_id": pid, "doi": doi, "title": paper["title"],
                   "authors": [author["author"]["display_name"] for author in paper["authorships"]],
                   "year": paper["publication_year"], "venue": location.get("display_name"),
                   "status": "pub" if paper["type"] == "article" else "wp",
                   "discovery_method": "official_affiliation_index",
                   "listing_url": stable_url(index_match["profile"]), "verification_url": paper["id"]}
            # An indexed abstract alone is insufficient for the primary-source evidence tier.
            metadata = registry.get(doi, {})
            add(row, plain_markup(metadata.get("work", {}).get("abstract")), metadata.get("url", ""))

        check_sources = local["sources"] + manual.get(pid, {}).get("sources", [])
        verified = [item for item in check_sources if item["status"] == "identity_checked"]
        checks.append({"person_id": pid, "sources": [
            {"url": stable_url(item["url"]), "role": item["role"], "status": item["status"]}
            for item in check_sources if stable_url(item["url"])],
            "state": ("papers_found" if matched else "profile_read_no_verified_paper" if verified else
                      "sources_inaccessible" if check_sources and all(item["status"] != "identity_unconfirmed"
                                                                      for item in check_sources) else
                      "identity_unconfirmed" if check_sources else "no_source"),
            "doi_leads": len(local["dois"]), "citation_queries": len(citations_by_person[pid]),
            "index_status": index_match.get("status")})
        works.extend(matched.values())
    save(args.output, {"checked_at": args.date, "summary": "School profiles, personal websites, public CVs and byline-validated publication records.",
                       "faculty": checks, "publications": works, "evidence": evidence})
    print(Counter(row["state"] for row in checks))
    print(f"{len(works)} faculty-paper links and {len(evidence)} primary-abstract tags.")


if __name__ == "__main__":
    main()
