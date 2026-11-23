"""Validate the snapshot, then build static index, school shards and exports."""

import argparse
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
import shutil

from sync import ROOT, href, load, save
from apply_followup import FULLTEXT, LEVELS, PRIMARY, REVIEWED, SIGNAL, merge_followups

STATUS = {
    REVIEWED: "Source reviewed",
    FULLTEXT: "Primary full-text evidence",
    PRIMARY: "Primary abstract evidence",
    SIGNAL: "Abstract signals available",
    "abstract_no_signal": "Abstract checked, no tag signal",
    "abstract_missing": "Paper listed, abstract unavailable",
    "no_papers": "No papers in source snapshot",
    "authorship_review": "Authorship needs review",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def csv_value(value):
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value


def export(directory, name, rows):
    save(directory / f"{name}.json", rows)
    fields = sorted({key for row in rows for key in row})
    with (directory / f"{name}.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows({key: csv_value(value) for key, value in row.items()} for row in rows)


def make_catalog(faculty, works, authors, evidence, taxonomy):
    tags = {tag for labels in taxonomy.values() for tag in labels}
    people, by_work = defaultdict(list), defaultdict(list)
    for mark in evidence:
        require(mark["paper_id"] in works and mark["tag"] in tags and href(mark["source"]),
                f"Broken evidence record: {mark}")
        require(mark["level"] in LEVELS, f"Invalid evidence level: {mark}")
        by_work[mark["paper_id"]].append(mark)
    pairs = set()
    for link in authors:
        pid, wid = link["person_id"], link["paper_id"]
        require(pid in faculty and wid in works and (pid, wid) not in pairs,
                f"Invalid authorship pair: {pid}, {wid}")
        pairs.add((pid, wid))
        people[pid].append(link)
    summaries = {}
    detail = {}
    for pid, person in faculty.items():
        papers, profile_tags, tag_counts, latest = [], {}, {level: Counter() for level in LEVELS}, {}
        links = people[pid]
        indexed = reviewed_count = 0
        for link in links:
            paper = works[link["paper_id"]]
            identity = link["identity"]
            allowed = set()
            if identity in ("upstream_byline_agrees", "orcid_agrees", "faculty_listing", REVIEWED) and not paper["retracted"]:
                indexed += paper["abstract_status"] == "indexed"
                allowed.update((SIGNAL, PRIMARY, FULLTEXT))
                if identity == REVIEWED:
                    allowed.add(REVIEWED)
            marks = [mark for mark in by_work[paper["id"]] if mark["level"] in allowed and
                     mark.get("person_id", pid) == pid]
            if any(mark["level"] == REVIEWED for mark in marks):
                reviewed_count += 1
                # The curator's scope for a reviewed paper is the source of
                # truth. Automatic suggestions cannot add extra public tags.
                marks = [mark for mark in marks if mark["level"] == REVIEWED]
            else:
                priority = {level: index for index, level in enumerate(LEVELS)}
                best = {}
                for mark in sorted(marks, key=lambda entry: priority[entry["level"]]):
                    best.setdefault(mark["tag"], mark)
                marks = list(best.values())
            for level in LEVELS:
                matched = sorted({mark["tag"] for mark in marks if mark["level"] == level})
                tag_counts[level].update(matched)
                for tag in matched:
                    latest[tag] = max(latest.get(tag, 0), paper["year"] or 0)
            if marks:
                profile_tags[paper["id"]] = {
                    level: sorted({mark["tag"] for mark in marks if mark["level"] == level})
                    for level in LEVELS}
            papers.append({**paper, "authorship": identity, "evidence": marks,
                           "listing_url": link.get("listing_url"), "discovery_method": link.get("discovery_method"),
                           "byline_check": link.get("followup_byline"), "identity_source": link.get("identity_source")})
        status = "no_papers"
        if tag_counts[REVIEWED]:
            status = REVIEWED
        elif tag_counts[FULLTEXT]:
            status = FULLTEXT
        elif tag_counts[PRIMARY]:
            status = PRIMARY
        elif tag_counts[SIGNAL]:
            status = SIGNAL
        elif indexed:
            status = "abstract_no_signal"
        elif links and all(link["identity"] == "review_needed" for link in links):
            status = "authorship_review"
        elif links:
            status = "abstract_missing"
        common = {key: person[key] for key in ("id", "name", "school", "scope", "rank", "unit",
                                               "area", "primary_fields", "education", "upstream_paper_count")}
        common.update({"status": status, "counts": tag_counts, "latest": latest,
                       "paper_count": len(papers), "abstracts_checked": indexed,
                       "source_reviewed_count": reviewed_count})
        summaries[pid] = {**common, "paper_tags": list(profile_tags.values())}
        detail[pid] = {**person, **common, "papers": sorted(
            papers, key=lambda p: (p["year"] or 0, p["title"]), reverse=True)}
    return summaries, detail


def audit(people, faculty, metadata):
    scope = defaultdict(Counter)
    school = defaultdict(Counter)
    track = defaultdict(Counter)
    for pid, person in people.items():
        status = person["status"]
        for group in (scope[person["scope"]], school[person["school"]]):
            group["total"] += 1
            group[status] += 1
        for name in person["primary_fields"]:
            if name.startswith("Marketing:"):
                track[name]["total"] += 1
                track[name][status] += 1
    return {**metadata, "faculty_total": len(people), "schools_total": len(school),
            "scope": scope, "school": school, "track": track,
            "status": Counter(row["status"] for row in people.values()),
            "coverage": {
                "faculty_with_papers": sum(bool(p["paper_count"]) for p in people.values()),
                "faculty_with_orcid_papers_only": sum(not faculty[pid]["upstream_paper_count"]
                    and p["paper_count"] and (faculty[pid].get("followup") or {}).get("state") != "papers_found"
                    for pid, p in people.items()),
                "faculty_with_abstracts": sum(bool(p["abstracts_checked"]) for p in people.values()),
                "faculty_with_reviewed_papers": sum(bool(p["source_reviewed_count"]) for p in people.values()),
                "authorship_pairs": sum(p["paper_count"] for p in people.values()),
                "pairs_with_indexed_abstract": sum(p["abstracts_checked"] for p in people.values()),
            },
            "placement": {
                "source": metadata["placement"],
                "shared_profile_url": sum(p.get("placement", {}).get("state") == "shared_profile_url"
                                          for p in faculty.values()),
                "identity_review": sum(p.get("placement", {}).get("state") == "identity_review"
                                       for p in faculty.values()),
                "institution_name_differences": sum(
                    any(row["institution_name_differs"] for row in p.get("placement", {}).get("candidates", []))
                    for p in faculty.values())}}


def build(out):
    source = ROOT / "data"
    faculty, works, authors, evidence, schools, taxonomy, metadata = (
        load(source / f"{name}.json") for name in (
            "faculty", "papers", "authorships", "evidence", "schools", "taxonomy", "metadata"))
    require(set(schools) == {person["school"] for person in faculty.values()}, "Invalid school coverage")
    for key, rows in (("faculty", faculty), ("papers", works)):
        require(all(k == row["id"] for k, row in rows.items()), f"Invalid {key} IDs")
    require(not (metadata.get("live_index_check") or {}).get("id_or_scope_differences"),
            "The roster differs from the live index. Review the snapshot before publishing.")
    followup, check_rows = merge_followups(faculty, works, authors, evidence, taxonomy)
    summary, detail = make_catalog(faculty, works, authors, evidence, taxonomy)
    report = audit(summary, faculty, metadata)
    if followup:
        report["followup"] = followup
    for filename in ("index.html", "app.js", "style.css", "filters.js"):
        out.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / "site" / filename, out / filename)
    save(out / "data.json", {"people": list(summary.values()), "schools": schools,
                            "taxonomy": taxonomy, "statuses": STATUS, "audit": report})
    shards = defaultdict(dict)
    for pid, person in detail.items():
        shards[person["school"]][pid] = person
    for school, rows in shards.items():
        save(out / "people" / f"{school}.json", rows)
    downloads = out / "download"
    for name, rows in (("faculty", [{**faculty[pid], **{k: v for k, v in r.items() if k != "paper_tags"}}
                                     for pid, r in summary.items()]),
                       ("papers", list(works.values())), ("authorships", authors), ("evidence", evidence)):
        export(downloads, name, rows)
    save(downloads / "coverage.json", report)
    if check_rows:
        export(downloads, "followup", check_rows)
    (out / ".nojekyll").touch()
    print(json.dumps({"total": report["faculty_total"], "schools": report["schools_total"],
                      "scope": report["scope"], "status": report["status"],
                      "coverage": report["coverage"], "crosscheck": report["placement"]}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "dist")
    build(parser.parse_args().out)
