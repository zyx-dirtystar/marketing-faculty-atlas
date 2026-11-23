"""Extract public abstracts tied to exact DOI and title matches."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import quote, urlencode

from collect_faculty_sources import allowed, decode, find_dois, pdf_content
from followup_http import Network, cache_rows, collect, plain_markup
from sync import ROOT, load, save, title_key

ABSTRACT = re.compile(r"(?:abstract|summary)", re.I)


def match_title(title, candidate):
    title, candidate = (re.sub(r"^express:\s*", "", text, flags=re.I) for text in (title, candidate))
    key, other = title_key(title), title_key(candidate)
    lead, other_lead = title_key(title.split(":")[0]), title_key(candidate.split(":")[0])
    return bool(len(key) >= 12 and (key == other or
                len(lead) >= 25 and lead == other_lead and (lead == key or lead == other) or
                (min(len(key), len(other)) >= 45 and (key in other or other in key)
                 and min(len(key), len(other)) / max(len(key), len(other)) > .84)))


def take_abstract(text):
    text = " ".join(text.split())
    text = re.sub(r"^\s*abstract\s*[:.\-]?\s*", "", text, count=1, flags=re.I)
    return text[:6000] if 85 <= len(text) <= 8500 else ""


def html_record(soup, target, title):
    meta = {}
    for row in soup.find_all("meta"):
        key = (row.get("name") or row.get("property") or "").lower()
        if key and row.get("content"):
            meta.setdefault(key, []).append(row["content"])
    ids = {doi for key in ("citation_doi", "dc.identifier", "dc.identifier.doi", "prism.doi", "bepress_citation_doi")
           for value in meta.get(key, []) for doi in find_dois(value)}
    titles = [value for key in ("citation_title", "dc.title", "og:title", "bepress_citation_title")
              for value in meta.get(key, [])]
    names = meta.get("citation_author", []) or meta.get("dc.creator", [])
    if ids and target not in ids:
        return "", names
    if not (target in ids or any(match_title(title, name) for name in titles)):
        return "", names
    sections = soup.select("section.abstract, section#abstract, div#abstract, div.abstractSection, "
                           "div.abstract, [data-title='Abstract'], [data-testid='abstract']")
    for section in sections:
        paras = [p.get_text(" ", strip=True) for p in section.find_all("p")]
        text = take_abstract(" ".join(paras) or section.get_text(" ", strip=True))
        if text:
            return text, names
    for heading in soup.find_all(["h2", "h3", "h4"]):
        if ABSTRACT.fullmatch(heading.get_text(" ", strip=True)):
            sibling = heading.find_next_sibling()
            if sibling and (text := take_abstract(sibling.get_text(" ", strip=True))):
                return text, names
    for key in ("citation_abstract", "dc.description.abstract", "eprints.abstract", "dc.description"):
        for value in meta.get(key, []):
            if text := take_abstract(plain_markup(value)):
                return text, names
    return "", names


def pdf_abstract(body, target, title):
    text = pdf_content(body)[:16000]
    if target not in find_dois(text) and title_key(title) not in title_key(text[:4500]):
        return ""
    match = re.search(r"(?is)(?:^|\n)\s*abstract\s*[:.\-—]?\s+(.{90,6000}?)"
                      r"(?=\n\s*(?:keywords?|jel classification|(?:1[.\s]+)?introduction)\b)", text)
    return take_abstract(match[1]) if match else ""


def parse_page(network, soup, url, doi, title):
    result, body = network.get(url, limit=5_000_000)
    if not body:
        return result
    if body.startswith(b"%PDF"):
        text, names = pdf_abstract(body, doi, title), []
    else:
        text, names = html_record(soup(decode(body, result["charset"]), "html.parser"), doi, title)
    return {**result, "status": "abstract_read" if text else "abstract_unavailable",
            "abstract": text, "authors": names}


def open_locations(network, dois):
    params = {"filter": "doi:" + "|".join(dois), "select": "doi,locations", "per-page": len(dois)}
    if key := os.environ.get("OPENALEX_API_KEY"):
        params["api_key"] = key
    status, body = network.get("https://api.openalex.org/works?" + urlencode(params), "application/json")
    if status["status"] != "read":
        return {}
    works = json.loads(body).get("results", [])
    result = {}
    for work in works:
        if not work["doi"]:
            continue
        urls = []
        for location in work["locations"]:
            source = location.get("source") or {}
            if not location["is_oa"] or source.get("type") != "repository":
                continue
            for url in (location.get("landing_page_url"), location.get("pdf_url")):
                if url and allowed(url) and url not in urls:
                    urls.append(url)
        result[work["doi"].removeprefix("https://doi.org/").lower()] = urls
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("registry", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--deps", type=Path)
    parser.add_argument("--locations", type=Path)
    parser.add_argument("--discover-locations", action="store_true")
    parser.add_argument("--queue", type=Path, default=ROOT / "data/followup/cohorts.json")
    args = parser.parse_args()
    if args.deps:
        sys.path.insert(0, str(args.deps.resolve()))
    from bs4 import BeautifulSoup

    entries = load(args.queue)["paper_queue"]
    papers = load(ROOT / "data/papers.json")
    registry = cache_rows(args.registry)
    locations = load(args.locations) if args.locations and args.locations.exists() else {}
    network = Network()
    titles = {papers[key]["doi"]: papers[key]["title"] for key in entries if papers[key].get("doi")}
    remaining = [doi for doi in titles if not registry.get(doi, {}).get("work", {}).get("abstract")]
    if args.discover_locations:
        pending = [doi for doi in remaining if doi not in locations]
        batches = [pending[i:i + 35] for i in range(0, len(pending), 35)]
        with ThreadPoolExecutor(max_workers=5) as pool:
            for matches in pool.map(lambda batch: open_locations(network, batch), batches):
                locations.update(matches)
        if args.locations:
            save(args.locations, locations)
        print(f"{sum(bool(row) for row in locations.values())} works with open repository copies", flush=True)

    def read(doi):
        publisher = "https://doi.org/" + quote(doi, safe="/")
        record = parse_page(network, BeautifulSoup, publisher, doi, titles[doi])
        attempted = [record["url"]]
        if record["status"] != "abstract_read":
            for url in locations.get(doi, [])[:2]:
                if url in attempted:
                    continue
                copy = parse_page(network, BeautifulSoup, url, doi, titles[doi])
                attempted.append(copy["url"])
                if copy["status"] == "abstract_read":
                    return {**copy, "kind": "public_manuscript", "attempted": attempted}
        return {**record, "kind": "publisher_page", "attempted": attempted}

    collect(remaining, read, args.output, workers=14)


if __name__ == "__main__":
    main()
