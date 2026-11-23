"""Find and read public methods sections for the deeper paper review."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import quote, urlencode, urljoin

from collect_faculty_sources import allowed, decode, find_dois, pdf_content
from collect_paper_sources import match_title
from followup_http import Network, collect
from sync import ROOT, load, save, title_key

HEADING = re.compile(r"^(?:(?:\d+\.)+?\s*|(?:\d+|[ivx]+)[.)]?\s+)?"
                     r"(?:study\s+\d+[a-z]?(?:\s*[:.\-–—].*)?|"
                     r"experiment(?:\s+\d+[a-z]?)?(?:\s+design)?|"
                     r"(?:research )?(?:design(?: and (?:methods?|procedure))?|method(?:s|ology)?)(?:\s+and\b.*)?|"
                     r"materials\s+and\s+methods|data(?: and (?:method\w*|identification|empirical strategy|"
                     r"estimation|analysis|model\w*))?|(?:identification|empirical|estimation) strategy|"
                     r"empirical (?:analysis|approach|specification|design|setting|application)|"
                     r"data (?:sources?|description|collection|and measures)|experimental (?:design|setup|"
                     r"procedures?|settings?|studies)|(?:model )?(?:estimation|identification)|"
                     r"(?:structural|analytical|formal|economic) model(?:s|ing)?|the model|"
                     r"(?:study |experimental )?procedures?|participants? and procedure|robustness checks|"
                     r"statistical analyses?|analysis plan)\s*[.:]?$", re.I)
STOP = re.compile(r"^(?:(?:\d+[.)]?\s+|[ivx]+\.\s+))?(?:references|bibliography|works cited|"
                  r"acknowledg\w+|competing interests)\s*$", re.I)
EXIT = re.compile(r"^(?:(?:\d+[.)]?\s+|[ivx]+\.\s+))?(?:results|discussion|conclusions?|"
                  r"limitations|general discussion|managerial implications|introduction|literature review|"
                  r"related (?:research|work)|theoretical background|hypotheses(?: development)?)\s*$", re.I)
PDF_LINK = re.compile(r"\b(?:full[- ]text|view pdf|download pdf|accepted manuscript|author manuscript|"
                      r"working paper|open access|document download)\b", re.I)


def headings_from_pdf(text):
    sections = []
    current = None
    for page, content in enumerate(text.split("\f"), 1):
        if not content.strip():
            continue
        for line in content.splitlines():
            small = " ".join(line.strip().split())
            if STOP.fullmatch(small):
                return sections
            if len(small) < 115 and HEADING.fullmatch(small):
                current = {"locator": f"Page {page}, {small}", "text": ""}
                sections.append(current)
            elif EXIT.fullmatch(small):
                current = None
            elif current is not None and len(current["text"]) < 11000:
                current["text"] += " " + small
    return sections


def pdf_sections(body, doi, title):
    text = pdf_content(body)
    opening = text[:9500]
    if not opening or (doi not in find_dois(opening) and title_key(title) not in title_key(opening)):
        return [], "pdf_title_unconfirmed"
    sections = headings_from_pdf(text)
    if not any(len(row["text"]) >= 130 for row in sections):
        return [], "pdf_no_method_heading"
    return sections, "fulltext_read"


def html_sections(soup, doi, title, url):
    meta = {}
    for node in soup.find_all("meta"):
        key = (node.get("name") or node.get("property") or "").lower()
        if key and node.get("content"):
            meta.setdefault(key, []).append(node["content"])
    ids = {value for key in ("citation_doi", "dc.identifier", "dc.identifier.doi", "prism.doi")
           for text in meta.get(key, []) for value in find_dois(text)}
    titles = [text for key in ("citation_title", "dc.title", "og:title") for text in meta.get(key, [])]
    titles.extend(h.get_text(" ", strip=True) for h in soup.find_all("h1"))
    if (ids and doi not in ids) or not (doi in ids or any(match_title(title, t) for t in titles)):
        return [], [], "html_title_unconfirmed"
    pdfs = [urljoin(url, target) for target in meta.get("citation_pdf_url", [])]
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if re.search(r"\.pdf(?:[?#]|$)", href, re.I) or PDF_LINK.search(a.get_text(" ", strip=True)):
            try:
                dest = urljoin(url, href)
            except ValueError:
                continue
            if allowed(dest) and dest != url and dest not in pdfs:
                pdfs.append(dest)
    article = soup.find("article") or soup.find("main") or soup
    sections = []
    current = None
    for node in article.find_all(["h2", "h3", "h4", "h5", "p"]):
        text = node.get_text(" ", strip=True)
        if node.name.startswith("h"):
            if STOP.fullmatch(text):
                break
            if HEADING.fullmatch(text):
                current = {"locator": text, "text": ""}
                sections.append(current)
            elif EXIT.fullmatch(text):
                current = None
        elif current is not None and len(current["text"]) < 14000:
            current["text"] += " " + text
    return sections, pdfs, "fulltext_read" if sections else "html_no_method_heading"


def get_locations(network, batch):
    params = {"select": "doi,locations,best_oa_location", "filter": "doi:" + "|".join(batch),
              "per-page": len(batch)}
    if key := os.environ.get("OPENALEX_API_KEY"):
        params["api_key"] = key
    status, content = network.get("https://api.openalex.org/works?" + urlencode(params),
                                  "application/json", limit=5_000_000)
    if not content:
        return {}
    matches = {}
    for work in json.loads(content).get("results", []):
        urls = []
        for loc in [work["best_oa_location"] or {}, *work["locations"]]:
            if not loc.get("is_oa"):
                continue
            for url in (loc.get("pdf_url"), loc.get("landing_page_url")):
                if url and allowed(url) and url not in urls:
                    urls.append(url)
        if work.get("doi"):
            matches[work["doi"].removeprefix("https://doi.org/").lower()] = urls
    return matches


def stable_page_url(url):
    if re.search(r"[?&](?:token|signature|authentication|x-amz-[\w-]+)=", url, re.I):
        return url.split("?", 1)[0]
    return url


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("queue", type=Path)
    parser.add_argument("locations", type=Path)
    parser.add_argument("cache", type=Path)
    parser.add_argument("--deps", type=Path)
    parser.add_argument("--targeted-locations", type=Path)
    args = parser.parse_args()
    if args.deps:
        sys.path.insert(0, str(args.deps.resolve()))
    from bs4 import BeautifulSoup

    keys = load(args.queue)["paper_queue"]
    papers = load(ROOT / "data/papers.json")
    titles = {papers[wid]["doi"]: papers[wid]["title"] for wid in keys if papers[wid].get("doi")}
    network = Network()
    if args.targeted_locations:
        locations = load(args.targeted_locations)
        titles = {doi: title for doi, title in titles.items() if doi in locations}
    else:
        locations = load(args.locations) if args.locations.exists() else {}
        remaining = [doi for doi in titles if doi not in locations]
        groups = [remaining[i:i + 35] for i in range(0, len(remaining), 35)]
        with ThreadPoolExecutor(max_workers=5) as pool:
            for result in pool.map(lambda group: get_locations(network, group), groups):
                locations.update(result)
        save(args.locations, locations)
    print(f"{sum(bool(row) for row in locations.values())}/{len(titles)} works with possible open full text.", flush=True)

    def read(doi):
        canonical = "https://doi.org/" + quote(doi, safe="/")
        queue = list(locations.get(doi, []))
        queue.append(canonical)
        tried = []
        attempts = []
        while queue and len(tried) < 5:
            url = queue.pop(0)
            if url in tried or not allowed(url):
                continue
            tried.append(url)
            result, body = network.get(url, limit=9_000_000)
            source = stable_page_url(result["url"])
            status = result["status"]
            if body:
                if body.startswith(b"%PDF"):
                    blocks, status = pdf_sections(body, doi, titles[doi])
                else:
                    soup = BeautifulSoup(decode(body, result["charset"]), "html.parser")
                    blocks, extras, status = html_sections(soup, doi, titles[doi], source)
                    queue = extras[:2] + queue
                blocks = [row for row in blocks if len(row["text"]) >= 130]
                if blocks:
                    return {"status": "fulltext_read", "source": source, "sections": blocks[:26],
                            "attempts": [*attempts, {"url": source, "status": status}]}
            attempts.append({"url": source, "status": status})
        return {"status": "fulltext_unavailable", "source": canonical, "attempts": attempts, "sections": []}

    # The DOI check is cheap for papers without an OpenAlex open copy, but keep
    # them in the queue so a publisher's freely accessible full text can count.
    collect(sorted(titles, key=lambda doi: (not bool(locations.get(doi)), doi)), read, args.cache, workers=16)


if __name__ == "__main__":
    main()
