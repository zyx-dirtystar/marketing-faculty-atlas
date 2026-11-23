"""Build the versioned factual snapshot and evidence from local source checkouts."""

import argparse
from collections import Counter, defaultdict
from datetime import date
import hashlib
import json
from pathlib import Path
import re
import subprocess
import unicodedata
from urllib.parse import urlsplit

from classify import VERSION, signals

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = "https://github.com/econ-faculty/econ-faculty.github.io"
ATLAS = "https://econ-faculty.github.io/"
PLACEMENT = "https://github.com/zyx-dirtystar/mkt-io-placement"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n",
                   encoding="utf-8")
    tmp.replace(path)


def commit(path):
    return subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()


def words(value):
    plain = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode().casefold()
    return re.findall(r"[a-z0-9]+", plain)


def title_key(value):
    return "".join(words(value))


def doi_key(paper):
    return (paper.get("doi") or "").lower().strip()


def href(value):
    parsed = urlsplit(value or "")
    return value if parsed.scheme in {"http", "https"} and parsed.hostname and not parsed.username else ""


def url_key(value):
    parsed = urlsplit(href(value))
    if not parsed.hostname:
        return ""
    path = parsed.path.rstrip("/").casefold()
    if not path and parsed.hostname.removeprefix("www.") in {
        "sites.google.com", "scholar.google.com", "orcid.org", "linkedin.com"
    }:
        return ""
    return parsed.hostname.casefold().removeprefix("www.") + path + (
        "?" + parsed.query if parsed.query else "")


def orcid_key(value):
    tail = (value or "").strip().rstrip("/").split("/")[-1]
    return "orcid.org/" + tail.upper() if re.fullmatch(r"\d{4}-\d{4}-\d{4}-\d{3}[\dX]", tail, re.I) else ""


def name_agrees(left, right):
    a, b = words(left), words(right)
    if min(len(a), len(b)) < 2 or a[-1] != b[-1]:
        return False
    if len(a[0]) > 1 and (a[0] == b[0] or
                         a[0].replace("ue", "u") == b[0].replace("ue", "u")):
        return True
    # Some records use an initial before a spelled-out given name.
    return bool({x for x in a[:-1] if len(x) > 1} & {x for x in b[:-1] if len(x) > 1})


def read_index(path):
    index = json.loads(path.read_text(encoding="utf-8").strip()
                       .removeprefix("window.EF = ").removesuffix(";"))
    rows = [dict(zip(index["cols"], values)) for values in index["people"]]
    rows = [row for row in rows if any(index["pfields"][i].split(":")[0] == "Marketing"
                                       for i in row["pfield"])]
    return index, rows


def source_audit(index, rows, live_path):
    if not live_path:
        return None
    live, live_rows = read_index(live_path)
    current = {row["id"]: index["unit_types"][row["unit_type"]] for row in rows}
    online = {row["id"]: live["unit_types"][row["unit_type"]] for row in live_rows}
    diff = sorted(current.keys() ^ online.keys() |
                  {key for key in current.keys() & online.keys() if current[key] != online[key]})
    return {"generation": live["generated"], "all": len(online),
            "share_link": sum(unit == "business" for unit in online.values()),
            "id_or_scope_differences": diff}


def read_roster(site, index, rows):
    details, institutions, people, entries = {}, {}, {}, {}
    for row in rows:
        pid = row["id"]
        institution = index["universities"][row["uni"]]
        uid = institution["id"]
        if uid not in details:
            details[uid] = load(site / "people" / f"{uid}.json")
            institutions[uid] = {k: institution[k] for k in ("id", "name", "short", "country", "region")}
        raw = details[uid][pid]
        links = {key: href(raw.get(key)) for key in
                 ("homepage_url", "profile_url", "cv_url", "google_scholar_url", "source_url")}
        fields = [index["pfields"][i] for i in row["pfield"]]
        paper_path = site / "pubs" / f"{pid}.json"
        entries[pid] = load(paper_path) if paper_path.exists() else []
        if len(entries[pid]) != sum(row["np"][:3]):
            raise ValueError(f"{pid}: source index and profile paper counts differ")
        people[pid] = {
            "id": pid, "name": row["name"], "school": uid, "title": raw.get("title"),
            "rank": index["ranks"][row["rank"]], "unit": row["unit"], "area": row["area"],
            "unit_type": index["unit_types"][row["unit_type"]],
            "scope": "share_link" if index["unit_types"][row["unit_type"]] == "business" else "cross_unit",
            "primary_fields": fields, "standard_fields": raw.get("fields_std") or [],
            "research_interests": raw.get("fields_raw") or "",
            "education": [{key: raw.get(f"{degree}_{key}") for key in ("institution", "year", "field")}
                          | {"degree": degree} for degree in ("phd", "ma", "ba")
                          if raw.get(f"{degree}_institution")],
            "year_joined": raw.get("year_joined"), "year_current_rank": raw.get("year_current_rank"),
            "orcid": raw.get("orcid"), "links": {k: v for k, v in links.items() if v},
            "upstream_url": f"{ATLAS}#/p/{pid}", "upstream_paper_count": len(entries[pid]),
        }
    return people, institutions, entries


def placement_matches(people, schools, checkout):
    if not checkout:
        return {}
    records = load(checkout / "data/faculty.json")["people"]
    index, names = defaultdict(list), defaultdict(list)
    manual = {(title_key(row["name"]), row["host_id"]): row["identity_evidence"]
              for row in load(checkout / "data/faculty-identities.json")}
    taxonomy = load(checkout / "data/taxonomy.json")
    track_ids = {title_key(alias): row["id"] for row in taxonomy["tracks"]
                 for alias in [row["id"], row["label"], *row.get("aliases", [])]}
    track_ids["quant"] = "qm"
    for old in records:
        name = title_key(old["name"])
        names[name].append(old)
        sources = manual.get((name, old.get("host_id")), {}).get("source_urls", [])
        keys = {url_key(old.get("homepage")), url_key(old.get("cv_url")), orcid_key(old.get("orcid"))}
        keys.update(url_key(url) for url in sources)
        for key in keys - {""}:
            index[key].append(old)
    matches = {}
    for pid, person in people.items():
        urls = {url_key(person["links"].get(field)) for field in ("homepage_url", "profile_url", "cv_url")}
        urls.add(orcid_key(person["orcid"]))
        exact = {old["id"]: old for key in urls - {""} for old in index[key]
                 if name_agrees(old["name"], person["name"])}
        candidates = exact or {old["id"]: old for old in names[title_key(person["name"])]}
        if not candidates:
            continue
        institution = title_key(schools[person["school"]]["name"])
        matches[pid] = {"state": "shared_profile_url" if len(exact) == 1 else "identity_review",
                        "candidates": [
                            {"id": old["id"], "name": old["name"], "checked_at": old.get("checked_at"),
                             "institution": (old.get("current") or {}).get("institution"),
                             "institution_name_differs": bool((old.get("current") or {}).get("institution"))
                             and institution not in title_key(old["current"]["institution"]),
                             "tracks": old.get("tracks") or [],
                             "standard_tracks": sorted({track_ids[title_key(track)] for track in old.get("tracks", [])
                                                        if title_key(track) in track_ids}),
                             "profile_url": href(old.get("homepage"))}
                            for old in candidates.values()]}
    return matches


def abstract_text(work):
    inverted = work.get("abstract_inverted_index") or {}
    return " ".join(word for _, word in sorted((pos, word) for word, positions in inverted.items()
                                               for pos in positions))


def work_key(paper):
    return (title_key(paper["t"]), tuple(title_key(name) for name in paper.get("a", [])))


def read_papers(entries, people, reviews):
    # A DOI always wins. DOI-less versions merge only when title and byline agree
    # and that fingerprint resolves to a single DOI.
    aliases = {doi: review["doi"] for review in reviews for doi in review.get("aliases", [])}
    by_title = defaultdict(set)
    for papers in entries.values():
        for paper in papers:
            if doi := doi_key(paper):
                by_title[work_key(paper)].add(aliases.get(doi, doi))
    works, authors = {}, {}
    for pid, papers in entries.items():
        for raw in papers:
            key = work_key(raw)
            doi = doi_key(raw)
            doi = aliases.get(doi, doi)
            if not doi and key[0] and key[1] and len(by_title[key]) == 1:
                doi = next(iter(by_title[key]))
            signature = [*key, None if key[1] else pid, None if key[1] else raw.get("y")]
            wid = "doi:" + doi if doi else "work:" + hashlib.sha256(
                json.dumps(signature).encode()).hexdigest()[:24]
            record = {"id": wid, "title": raw["t"], "year": raw.get("y"),
                      "authors": raw.get("a") or [], "doi": doi or None, "venue": raw.get("j"),
                      "url": "https://doi.org/" + doi if doi else href(raw.get("l")),
                      "status": raw["c"], "versions": [], "discovery": raw.get("discovery", "econ_atlas")}
            if wid not in works:
                works[wid] = record
            elif raw["c"] == "pub" and works[wid]["status"] != "pub":
                record["versions"] = works[wid]["versions"]
                works[wid] = record
            version = {"title": raw["t"], "status": raw["c"], "year": raw.get("y"),
                       "doi": doi_key(raw) or None, "url": href(raw.get("l"))}
            if version not in works[wid]["versions"]:
                works[wid]["versions"].append(version)
            byline = [name for name in raw.get("a", []) if name_agrees(people[pid]["name"], name)]
            link = authors.setdefault((pid, wid), {
                "person_id": pid, "paper_id": wid, "identity": "review_needed",
                "upstream_statuses": []})
            if raw.get("discovery") == "openalex_exact_orcid":
                link["identity"] = "orcid_agrees"
            elif len(byline) == 1:
                link["identity"] = "upstream_byline_agrees"
            if not raw.get("discovery") and raw["c"] not in link["upstream_statuses"]:
                link["upstream_statuses"].append(raw["c"])
    return works, authors


def apply_reviews(works, authors, people, reviews, allowed_tags, checked_at):
    marks = defaultdict(list)
    for review in reviews:
        wid = "doi:" + review["doi"]
        if wid not in works:
            raise ValueError(f"Reviewed DOI missing from roster papers: {wid}")
        for pid in review["people"]:
            if pid not in people:
                raise ValueError(f"Unknown reviewed faculty ID: {pid}")
            link = authors.setdefault((pid, wid), {"person_id": pid, "paper_id": wid, "upstream_statuses": []})
            if not any(name_agrees(people[pid]["name"], name) for name in works[wid]["authors"]):
                raise ValueError(f"Check reviewed byline: {pid}, {wid}")
            link["identity"] = "source_reviewed"
        seen_tags = set()
        for tags, note in review["claims"]:
            for tag in tags:
                if tag not in allowed_tags or tag in seen_tags:
                    raise ValueError(f"Unknown or duplicated review tag {tag} in {wid}")
                seen_tags.add(tag)
                marks[wid].append({"tag": tag, "level": "source_reviewed", "note": note,
                                   "source": review["source"], "locator": review["locator"],
                                   "checked_at": review.get("checked_at", checked_at)})
    return marks


def read_cache(path):
    abstracts = {}
    if path:
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                abstracts.update(json.loads(line))
    return abstracts


def merge_discovery(discovery, entries, people, cache):
    for pid, result in discovery.items():
        if pid not in people or people[pid]["upstream_paper_count"]:
            continue
        orcid = orcid_key(people[pid]["orcid"])
        if not orcid or orcid != orcid_key(result.get("orcid")):
            continue
        people[pid]["orcid_discovery"] = result["state"]
        for work in result["papers"]:
            if not any(orcid_key(row["author"].get("orcid")) == orcid and
                       name_agrees(row["author"].get("display_name"), people[pid]["name"])
                       for row in work["authorships"]):
                continue
            doi = work["doi"].removeprefix("https://doi.org/").lower()
            location = (work.get("primary_location") or {}).get("source") or {}
            entries[pid].append({"t": work["title"], "doi": doi, "l": work["doi"],
                                 "a": [r["author"]["display_name"] for r in work["authorships"]],
                                 "c": "pub" if work["type"] == "article" else "wp",
                                 "j": location.get("display_name"), "y": work["publication_year"],
                                 "discovery": "openalex_exact_orcid"})
            cache[doi] = work


def enrich(works, authors, people, marks, cache, checked_at):
    author_groups = defaultdict(list)
    for (pid, wid), link in authors.items():
        author_groups[wid].append((pid, link))
    evidence = []
    for wid, paper in works.items():
        doi = paper["doi"]
        work = cache.get(doi) or {}
        abstract = abstract_text(work)
        paper["openalex_url"] = href(work.get("id"))
        paper["abstract_status"] = (
            "indexed" if abstract else "unavailable" if doi in cache else
            "unchecked_doi" if doi else "no_doi")
        paper["retracted"] = bool(work.get("is_retracted"))
        signal_tags = []
        if abstract and not paper["retracted"]:
            signal_tags = signals(paper["title"], abstract, paper["openalex_url"])
        reviewed = [] if paper["retracted"] else marks[wid]
        # A pair keeps its level. Source review of the same paper counts only
        # for people whose authorship was expressly checked in that review.
        evidence.extend({"paper_id": wid, **mark} for mark in reviewed)
        evidence.extend({"paper_id": wid, "checked_at": checked_at, **mark} for mark in signal_tags)
        byline = [author.get("author", {}).get("display_name", "")
                  for author in work.get("authorships", [])]
        for pid, link in author_groups[wid]:
            if link["identity"] == "source_reviewed":
                continue
            if (link["identity"] == "upstream_byline_agrees" and byline and
                    not any(name_agrees(people[pid]["name"], name) for name in byline)):
                link["identity"] = "review_needed"
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", required=True, type=Path)
    parser.add_argument("--placement", type=Path)
    parser.add_argument("--abstracts", type=Path)
    parser.add_argument("--orcid-discovery", type=Path)
    parser.add_argument("--live-index", type=Path)
    parser.add_argument("--checked-at", required=True, type=date.fromisoformat)
    args = parser.parse_args()
    site = args.upstream / "site"
    index, rows = read_index(site / "data.js")
    people, schools, entries = read_roster(site, index, rows)
    reviews = load(ROOT / "data/pilot.json")
    taxonomy = load(ROOT / "data/taxonomy.json")
    cache = read_cache(args.abstracts)
    doi_lookups = len(cache)
    if args.orcid_discovery:
        merge_discovery(load(args.orcid_discovery), entries, people, cache)
    works, authors = read_papers(entries, people, reviews)
    checked_at = args.checked_at.isoformat()
    allowed = {tag for labels in taxonomy.values() for tag in labels}
    marks = apply_reviews(works, authors, people, reviews, allowed, checked_at)
    evidence = enrich(works, authors, people, marks, cache, checked_at)
    crosscheck = placement_matches(people, schools, args.placement)
    for pid, result in crosscheck.items():
        people[pid]["placement"] = result
    metadata = {
        "checked_at": checked_at, "upstream": UPSTREAM, "upstream_commit": commit(args.upstream),
        "upstream_generation": index["generated"], "placement": PLACEMENT,
        "placement_commit": commit(args.placement) if args.placement else None,
        "live_index_check": source_audit(index, rows, args.live_index),
        "abstract_provider": "OpenAlex", "classifier": VERSION,
        "doi_lookups": doi_lookups, "paper_counts": dict(Counter(p["abstract_status"] for p in works.values())),
        "orcid_lookup_status": dict(Counter(p["orcid_discovery"] for p in people.values() if "orcid_discovery" in p)),
    }
    data = ROOT / "data"
    for name, rows in (("metadata", metadata), ("schools", schools), ("faculty", people),
                       ("papers", works), ("authorships", list(authors.values())), ("evidence", evidence)):
        save(data / f"{name}.json", rows)
    print(f"{len(people)} faculty; {len(works)} distinct works; {len(evidence)} paper-tag evidence rows.")


if __name__ == "__main__":
    main()
