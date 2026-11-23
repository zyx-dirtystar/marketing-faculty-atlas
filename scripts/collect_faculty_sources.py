"""Read faculty-owned publication lists, official profiles and publicly linked CVs."""

import argparse
from collections import defaultdict
from pathlib import Path
import re
import shutil
import subprocess
import sys
from urllib.parse import unquote, urljoin, urlsplit

from followup_http import Network, collect
from sync import ROOT, href, load, title_key, url_key, words

DOI = re.compile(r"(?<!\w)10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)
CV = re.compile(r"\b(?:curriculum vitae|cv|lebenslauf|簡歷|简历|履歴書)\b", re.I)
RESEARCH_PORTAL = re.compile(r"\b(?:research (?:portal|profile|output)|institutional repository|"
                             r"view all \d+ research outputs?|publication list|profil de recherche|"
                             r"tous les r[eé]sultats de recherche)\b", re.I)
PUBLICATIONS = re.compile(
    r"\b(?:publications?|selected works|working papers?|research outputs?|research papers?|bibliography|"
    r"publikationen|ver[oö]ffentlichungen|publikasjoner|publicaciones|pubblicazioni|publikationer)\b|"
    r"发表论文|研究成果|学术成果|代表性论文|出版物|著書|論文", re.I)
PAPER_SECTION = re.compile(r"^(?:\d*\.?\s*)?(?:(?:refereed |peer.reviewed |selected |journal |academic )?"
                           r"publications|research papers|articles|working papers|publikationen|"
                           r"publicaciones|pubblicazioni|发表论文|研究成果)(?:\s*[::：].*)?$", re.I)


def name_present(name, text):
    name_tokens = words(name)
    haystack = " ".join(words(text[:50000]))
    if not name_tokens:
        return bool(name and name in text[:50000])
    variants = [" ".join(name_tokens), " ".join(reversed(name_tokens))]
    if len(name_tokens) > 2 and len(name_tokens[-1]) > 2:
        variants.append(f"{name_tokens[0]} {name_tokens[-1]}")
    return any(re.search(rf"\b{re.escape(variant)}\b", haystack) for variant in variants)


def find_dois(text):
    result = set()
    for match in DOI.finditer(unquote(text)):
        doi = match.group(0).lower().rstrip(".;:")
        while doi.endswith(")") and doi.count(")") > doi.count("("):
            doi = doi[:-1]
        if not doi.endswith("/"):
            result.add(doi)
    return result


def decode(body, charset):
    try:
        return body.decode(charset, "replace")
    except LookupError:
        return body.decode("utf-8", "replace")


def allowed(url):
    try:
        host = urlsplit(href(url)).hostname or ""
    except ValueError:
        return False
    return "." in host and not host.endswith((".local", ".internal")) and not re.fullmatch(r"[\d.]+", host)


def title_candidates(content):
    snippets = set()
    for line in content:
        line = " ".join(line.split()).strip("•–— ")
        if 30 <= len(line) <= 300 and (re.search(r"\b(?:19|20)\d{2}\b", line)
                                      or re.search(r"\b(?:journal|review|marketing science|management science)\b", line, re.I)):
            snippets.add(line)
    return sorted(snippets)[:35]


def pdf_content(body):
    binary = shutil.which("pdftotext")
    if not binary:
        return ""
    try:
        process = subprocess.run([binary, "-layout", "-", "-"], input=body, capture_output=True,
                                 timeout=16, check=True)
    except (subprocess.SubprocessError, OSError):
        return ""
    return process.stdout.decode("utf-8", "replace")


class FacultySources:
    def __init__(self, faculty, soup, extra_sources=None, deep=False):
        self.faculty = faculty
        self.soup = soup
        self.extra_sources = extra_sources or {}
        self.deep = deep
        self.network = Network()

    def read_publication(self, source, result, title, people):
        meta = {}
        for node in source.find_all("meta"):
            key = (node.get("name") or node.get("property") or "").lower()
            if key and node.get("content"):
                meta.setdefault(key, []).append(node["content"])
        headings = source.find(["h1", "h2"])
        actual_title = next(iter(meta.get("citation_title", [])), headings.get_text(" ", strip=True) if headings else title)
        names = meta.get("citation_author", []) or meta.get("dc.creator", []) or meta.get("bepress_citation_author", [])
        if not names:
            for node in source.select(".persons .person, .authors .person, .persons a.link, "
                                      ".result-container .relations.persons li, [itemprop='author']"):
                label = node.get_text(" ", strip=True)
                if label.strip() and label not in names:
                    names.append(label)
        if not any(name_present(person, byline) for person in people for byline in names):
            return {**result, "status": "publication_byline_unconfirmed"}, []
        meta_ids = {doi for key in ("citation_doi", "dc.identifier", "prism.doi")
                    for text in meta.get(key, []) for doi in find_dois(text)}
        canonical_ids = find_dois(result["url"])
        dois = sorted(meta_ids or canonical_ids)
        if not dois:
            for a in source.find_all("a", href=True):
                dest = a["href"]
                if "doi.org/" in dest.lower():
                    meta_ids.update(find_dois(dest))
            if len(meta_ids) == 1:
                dois = sorted(meta_ids)
        year = next((value[:4] for key in ("citation_publication_date", "citation_date", "dc.date.issued")
                     for value in meta.get(key, []) if re.match(r"(?:19|20)\d{2}", value)), None)
        venue = next(iter(meta.get("citation_journal_title", [])), None)
        # A DOI-free record can qualify only when its own metadata explicitly
        # establishes a journal article, preprint, or institutional working paper.
        type_ = " ".join(meta.get("dc.type", []) + meta.get("eprints.type", []))
        article_mark = bool(re.search(r"\b(?:journal article|working paper|preprint)\b", type_, re.I) or venue)
        candidate = {"title": actual_title, "authors": names, "year": int(year) if year else None,
                     "venue": venue, "status": "wp" if re.search(r"working paper|preprint", type_, re.I) else "pub"}
        return {**result, "status": "publication_byline_checked", "dois": dois,
                "publication": candidate if article_mark and len(actual_title) >= 16 else None}, []

    def read_page(self, url, role, names):
        if not allowed(url):
            return {"url": url, "role": role, "status": "invalid_url", "dois": [], "citations": []}, []
        result, body = self.network.get(url, limit=4_000_000)
        result = {**result, "role": role, "requested": url, "dois": [], "citations": []}
        if not body:
            return result, []
        if body.startswith(b"%PDF"):
            text = pdf_content(body)
            if not text:
                return {**result, "status": "pdf_text_unavailable"}, []
            if role == "cv" and any(name_present(name, text[:4500]) for name in names):
                lines = text.splitlines()
                starts = [i for i, line in enumerate(lines) if PAPER_SECTION.match(line.strip())]
                relevant = lines[min(starts):] if starts else lines
                return {**result, "status": "identity_checked", "dois": sorted(find_dois(text)),
                        "citations": title_candidates(relevant)}, []
            if self.deep and role == "publication_record" and any(name_present(name, text[:7000]) for name in names):
                return {**result, "status": "publication_byline_checked",
                        "dois": sorted(find_dois(text[:7000]))[:2]}, []
            return {**result, "status": "identity_unconfirmed"}, []

        source = self.soup(decode(body, result["charset"]), "html.parser")
        for node in source(["script", "style", "noscript", "template"]):
            node.decompose()
        if role == "publication_record":
            return self.read_publication(source, result, "", names)
        headings = source.find_all(["title", "h1"])
        header = " ".join(node.get_text(" ", strip=True) for node in headings)
        text = source.get_text(" ", strip=True)
        identity = any(name_present(name, header) or role in {"home", "profile"} and
                       name_present(name, text[:7200]) and
                       any(word in title_key(urlsplit(url).path) for word in words(name)[-1:]) for name in names)
        if role in {"publication_list", "cv"} and any(name_present(name, text[:5500]) for name in names):
            identity = True
        if role == "directory":
            identity = False

        links, anchor_dois = [], set()
        for a in source.find_all("a", href=True):
            try:
                dest = urljoin(result["url"], a["href"])
            except ValueError:
                continue
            label = a.get_text(" ", strip=True)
            if not allowed(dest) or url_key(dest) == url_key(result["url"]):
                continue
            if not identity:
                if role == "directory" and label and any(name_present(name, label) for name in names):
                    links.append(("profile", dest))
                continue
            anchor_dois.update(find_dois(dest) if "doi.org/" in dest or self.deep else ())
            if CV.search(label) and len(label) < 100:
                links.append(("cv", dest))
            elif PUBLICATIONS.search(label) and len(label) < 70:
                if urlsplit(dest).hostname == urlsplit(result["url"]).hostname:
                    links.append(("publication_list", dest))
            elif self.deep and RESEARCH_PORTAL.search(label) and len(label) < 115:
                links.append(("publication_list", dest))
            elif self.deep and len(label) >= 20 and re.search(r"/(?:publications|outputs|facpub|researchoutputs)/[^/?#]+", dest, re.I):
                links.append(("publication_record", dest))
            elif re.fullmatch(r"(?:personal |personal research )?(?:website|homepage|home page)", label, re.I):
                links.append(("home", dest))
        if not identity:
            return {**result, "status": "identity_unconfirmed"}, links
        main = source.find("main") or source.find("article") or source
        scope = main.get_text(" ", strip=True)
        anchor_dois.update(find_dois(scope))
        possible = (node.get_text(" ", strip=True) for node in main.find_all(["li", "p", "article"]))
        citations = title_candidates(possible) if PUBLICATIONS.search(scope) else []
        return {**result, "status": "identity_checked", "dois": sorted(anchor_dois),
                "citations": citations}, links

    def __call__(self, pid):
        person = self.faculty[pid]
        names = [person["name"], *person.get("publication_aliases", [])]
        sources = person["links"]
        links = [(role, sources.get(key)) for role, key in (
            ("profile", "profile_url"), ("home", "homepage_url"), ("cv", "cv_url"))]
        links = self.extra_sources.get(pid, []) + links
        links = [(role, url, None) for role, url in links]
        attempted, found = [], defaultdict(list)
        seen = set()
        position = 0
        while position < len(links) and len(seen) < (13 if self.deep else 9):
            role, url, origin = links[position]
            position += 1
            if not url or not allowed(url) or url_key(url) in seen:
                continue
            seen.add(url_key(url))
            result, inferred = self.read_page(url, role, names)
            if self.deep and origin:
                result["via"] = origin
            attempted.append(result)
            for doi in result["dois"]:
                found[doi].append(result["url"])
            links.extend((kind, destination, origin or result["url"]) for kind, destination in inferred)
        if not any(item["status"] == "identity_checked" for item in attempted) and sources.get("source_url"):
            result, from_directory = self.read_page(sources["source_url"], "directory", names)
            attempted.append(result)
            for role, url in from_directory[:2]:
                if url_key(url) in seen:
                    continue
                article, _ = self.read_page(url, role, names)
                attempted.append(article)
                for doi in article["dois"]:
                    found[doi].append(article["url"])
        return {"status": "checked" if attempted else "no_source",
                "sources": attempted, "dois": dict(found)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cache", type=Path)
    parser.add_argument("--deps", type=Path)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    if args.deps:
        sys.path.insert(0, str(args.deps.resolve()))
    from bs4 import BeautifulSoup

    cohort = load(ROOT / "data/followup/cohorts.json")["publication_search"]
    faculty = load(ROOT / "data/faculty.json")
    collect(cohort[:args.limit], FacultySources(faculty, BeautifulSoup), args.cache, workers=20)


if __name__ == "__main__":
    main()
