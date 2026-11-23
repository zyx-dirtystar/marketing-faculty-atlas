"""Publish confirmed publication links and source-search outcomes from local caches."""

import argparse
from collections import Counter, defaultdict
import hashlib
from pathlib import Path
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from apply_followup import PRIMARY
from followup_http import cache_rows, plain_markup
from make_method_batch import exact_name, record_names
from primary_methods import extract
from sync import ROOT, href, load, orcid_key, save, title_key, url_key

TYPES = {"journal-article", "posted-content", "proceedings-article"}


def stable_url(url):
    parsed = urlsplit(href(url))
    if not parsed.netloc:
        return ""
    query = [(field, value) for field, value in parse_qsl(parsed.query, keep_blank_values=True)
             if not re.search(r"token|signature|password|secret|^x-amz-|^key$|^auth$", field, re.I)]
    return urlunsplit(parsed._replace(query=urlencode(query), fragment=""))


def organization(url):
    parts = (urlsplit(href(url)).hostname or "").split(".")
    endings = {"ac", "edu", "gov", "org", "com", "co"}
    take = 3 if len(parts) >= 3 and len(parts[-1]) == 2 and parts[-2] in endings else 2
    return ".".join(parts[-take:])


def owner_source(person, url, additional):
    key = url_key(url)
    if not key:
        return False
    trusted = [url_key(address) for address in additional if url_key(address)]
    urls = person["links"]
    if (identifier := orcid_key(person.get("orcid"))) and key == identifier.lower():
        return True
    for role in ("homepage_url", "cv_url", "profile_url"):
        if source_key := url_key(urls.get(role)):
            trusted.append(source_key)
    university = organization(urls.get("profile_url") or urls.get("source_url"))
    return ((university and organization(url) == university) or
            any(key == address or key.startswith(address.rstrip("/") + "/") for address in trusted))


def publication(registry, person, doi, source, method, citation=None):
    type_ = registry.get("type")
    if type_ not in TYPES or not registry.get("title") or registry.get("DOI", "").lower() != doi:
        return None
    names = record_names(registry)
    accepted = [person["name"], *person.get("publication_aliases", [])]
    identifier = orcid_key(person.get("orcid"))
    orcid_match = identifier and sum(orcid_key(row.get("ORCID")) == identifier for row in registry.get("author", [])) == 1
    if not orcid_match and sum(any(exact_name(name, alias) for alias in accepted) for name in names) != 1:
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
    parser.add_argument("--extra-sources", type=Path, action="append", default=[])
    parser.add_argument("--orcid-sources", type=Path)
    parser.add_argument("--orcid-profiles", type=Path)
    parser.add_argument("--aliases", type=Path)
    parser.add_argument("--verified-sources", type=Path)
    parser.add_argument("--previous", type=Path, action="append", default=[])
    parser.add_argument("--deep", action="store_true")
    parser.add_argument("--date", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sources = cache_rows(args.faculty_sources)
    for path in (*args.extra_sources, args.orcid_sources):
        for pid, row in (cache_rows(path).items() if path else []):
            initial = sources.get(pid, {"sources": [], "dois": {}})
            dois = {doi: list(dict.fromkeys(initial["dois"].get(doi, []) + row["dois"].get(doi, [])))
                    for doi in initial["dois"].keys() | row["dois"].keys()}
            sources[pid] = {**row, "sources": [*initial["sources"], *row["sources"]], "dois": dois}
    registry = {}
    for file in args.registries:
        registry.update(cache_rows(file))
    citations_by_person = defaultdict(list)
    for row in cache_rows(args.citations).values() if args.citations else []:
        citations_by_person[row["person_id"]].append(row)
    affiliations = cache_rows(args.affiliations) if args.affiliations else {}
    manual = load(args.manual) if args.manual else {}
    faculty = load(ROOT / "data/faculty.json")
    for pid, item in (load(args.orcid_profiles).items() if args.orcid_profiles else []):
        if not faculty[pid].get("orcid"):
            faculty[pid]["orcid"] = item["orcid"]
    verified_sources = load(args.verified_sources) if args.verified_sources else {}
    for pid, aliases in (load(args.aliases).items() if args.aliases else []):
        faculty[pid]["publication_aliases"] = aliases
    baseline = load(ROOT / "data/papers.json")
    prior = defaultdict(set)
    for path in args.previous:
        for row in load(path)["publications"]:
            prior[row["person_id"]].add(title_key(row["title"]))
    plan = "deep-review-plan.json" if args.deep else "cohorts.json"
    cohort = load(ROOT / "data/followup" / plan)["publication_search"]
    works, evidence, checks = [], [], []
    for pid in cohort:
        if pid not in sources and pid not in manual:
            continue
        local = sources.get(pid, {"sources": [], "dois": {}})
        author = faculty[pid]
        matched = {}

        def trusted(url):
            return not args.deep or owner_source(author, url, verified_sources.get(pid, []))

        def add(row, abstract, evidence_url):
            if not row or not row["listing_url"]:
                return
            wid = "doi:" + row["doi"] if row.get("doi") else row["paper_id"]
            if wid in matched or title_key(row["title"]) in prior[pid] or baseline.get(wid, {}).get("retracted"):
                return
            matched[wid] = row
            for mark in extract(abstract):
                evidence.append({"person_id": pid, "paper_id": wid,
                                 "level": PRIMARY, "source": evidence_url,
                                 "locator": f"Publisher-deposited abstract via Crossref, sentence {mark['sentence']}",
                                 **mark})

        for doi, urls in sorted({**local["dois"], **manual.get(pid, {}).get("dois", {})}.items()):
            source_url = next((url for url in urls if trusted(url)), None)
            if not source_url:
                continue
            metadata = registry.get(doi, {})
            record = metadata.get("work", {})
            discovery = "orcid_works" if urlsplit(source_url).hostname == "orcid.org" else "faculty_doi"
            row = publication(record, author, doi, source_url, discovery)
            add(row, plain_markup(record.get("abstract")), metadata.get("url", ""))
        for citation in citations_by_person[pid]:
            if not trusted(citation["url"]):
                continue
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

        if args.deep:
            known_titles = {title_key(row["title"]) for row in matched.values()}
            for item in local["sources"]:
                candidate = item.get("publication")
                if not candidate or not trusted(item["url"]) or title_key(candidate["title"]) in known_titles:
                    continue
                url = stable_url(item["url"])
                digest = hashlib.sha256(url_key(url).encode()).hexdigest()[:24]
                add({**candidate, "person_id": pid, "paper_id": "source:" + digest,
                     "discovery_method": "institutional_publication_record",
                     "listing_url": url, "verification_url": url}, "", "")
                known_titles.add(title_key(candidate["title"]))

        check_sources = local["sources"] + manual.get(pid, {}).get("sources", [])
        check_sources = [{**item, "status": "identity_unconfirmed"} if
                         item["status"] in {"identity_checked", "publication_byline_checked"} and
                         not trusted(item["url"]) else item for item in check_sources]
        verified = [item for item in check_sources
                    if item["status"] in {"identity_checked", "publication_byline_checked"}]
        checks.append({"person_id": pid, "sources": [
            {"url": stable_url(item["url"]), "role": item["role"], "status": item["status"]}
            for item in check_sources if stable_url(item["url"])],
            "state": ("papers_found" if matched or prior[pid] else "profile_read_no_verified_paper" if verified else
                      "sources_inaccessible" if check_sources and all(
                          item["status"] not in {"identity_unconfirmed", "orcid_name_mismatch",
                                                 "publication_byline_unconfirmed"} for item in check_sources) else
                      "identity_unconfirmed" if check_sources else "no_source"),
            "doi_leads": len(local["dois"]), "citation_queries": len(citations_by_person[pid]),
            "index_status": index_match.get("status"), **({"deep_review": True} if args.deep else {})})
        works.extend(matched.values())
    save(args.output, {"checked_at": args.date, "summary": "School profiles, personal websites, public CVs and byline-validated publication records.",
                       "faculty": checks, "publications": works, "evidence": evidence})
    print(Counter(row["state"] for row in checks))
    print(f"{len(works)} faculty-paper links and {len(evidence)} primary-abstract tags.")


if __name__ == "__main__":
    main()
