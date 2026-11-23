"""Join fixed-cohort research batches into an in-memory, validated release."""

from collections import Counter, defaultdict

from sync import ROOT, href, load

REVIEWED = "source_reviewed"
PRIMARY = "primary_abstract"
SIGNAL = "abstract_signal"
LEVELS = (REVIEWED, PRIMARY, SIGNAL)


def check(condition, message):
    if not condition:
        raise ValueError(message)


def merge_followups(faculty, works, authors, evidence, taxonomy):
    directory = ROOT / "data/followup"
    cohorts_path = directory / "cohorts.json"
    if not cohorts_path.exists():
        return {}, []
    cohort = load(cohorts_path)
    methods = cohort["method_review"]
    missing = set(cohort["publication_search"])
    original_queue = set(cohort["paper_queue"])
    extra_plan = directory / "alternate-method-plan.json"
    extra_methods = load(extra_plan)["method_review"] if extra_plan.exists() else {}
    check(set(extra_methods) <= set(methods), "Alternate review is outside the methods cohort")
    extra_queue = {wid for rows in extra_methods.values() for wid in rows}
    queue = original_queue | extra_queue
    check(len(methods) == 777 and len(missing) == 469 and not missing.intersection(methods),
          "The frozen follow-up cohorts changed")
    check((set(methods) | missing) <= set(faculty) and queue <= set(works), "Follow-up sources changed")
    links = {(row["person_id"], row["paper_id"]): row for row in authors}
    by_person = defaultdict(dict)
    checks, searches, tested = {}, {}, {}
    corrections = defaultdict(dict)
    batches = []
    tags = {tag for group in taxonomy.values() for tag in group}

    for path in sorted(directory.glob("batch-*.json")):
        batch = load(path)
        date = batch["checked_at"]
        batches.append({"id": path.stem, "checked_at": date, "summary": batch["summary"]})
        for item in batch.get("papers", []):
            wid = item["paper_id"]
            check(wid in queue, f"Paper outside fixed cohort: {wid}")
            if checks.get(wid, {}).get("state", "").startswith("manual_") and not item["state"].startswith("manual_"):
                continue
            checks[wid] = {"paper_id": wid, "state": item["state"], "source": item.get("source"),
                           "checked_at": date, "batch": path.stem}
        for row in batch.get("publications", []):
            pid = row["person_id"]
            title = row["title"]
            doi = row.get("doi")
            wid = "doi:" + doi if doi else row["paper_id"]
            paper_url = "https://doi.org/" + doi if doi else row["verification_url"]
            check(pid in missing and (doi or wid.startswith("source:")) and
                  href(row["listing_url"]) and href(row["verification_url"]),
                  f"Unverifiable discovered publication: {pid} / {wid}")
            paper = works.setdefault(wid, {
                "id": wid, "title": title, "year": row["year"], "authors": row["authors"],
                "doi": doi, "venue": row["venue"], "url": paper_url,
                "status": row["status"], "versions": [], "discovery": "faculty_publications",
                "abstract_status": "unavailable", "openalex_url": "", "retracted": False,
            })
            if paper["retracted"]:
                continue
            if (pid, wid) not in links:
                link = {"person_id": pid, "paper_id": wid, "identity": "faculty_listing",
                        "upstream_statuses": []}
                authors.append(link)
                links[pid, wid] = link
            links[pid, wid].update({"listing_url": row["listing_url"],
                                    "verification_url": row["verification_url"],
                                    "discovery_method": row["discovery_method"],
                                    "followup_batch": path.stem})
        for row in batch.get("faculty", []):
            pid = row["person_id"]
            check(pid in missing, f"Publication search outside fixed cohort: {pid}")
            previous = searches.get(pid, {})
            prior_sources = previous.get("sources", [])
            combined = {(item["role"], item["url"]): item for item in [*prior_sources, *row["sources"]]}
            searches[pid] = {**previous, **row, "sources": list(combined.values()),
                             "batch": path.stem, "checked_at": date}
        for mark in batch.get("evidence", []):
            wid, pid = mark["paper_id"], mark["person_id"]
            level = mark["level"]
            check(pid in methods or pid in missing, f"Unknown follow-up person {pid}")
            check((pid, wid) in links and links[pid, wid]["identity"] != "review_needed"
                  and not works[wid]["retracted"], f"Invalid follow-up evidence: {pid} / {wid}")
            check(level in (REVIEWED, PRIMARY) and mark["tag"] in tags and href(mark["source"]),
                  f"Invalid follow-up annotation: {mark}")
            if level == REVIEWED:
                links[pid, wid]["identity"] = REVIEWED
            tested[pid, wid, mark["tag"], level] = {**mark, "checked_at": date, "batch": path.stem}
        for decision in batch.get("author_checks", []):
            pid, wid = decision["person_id"], decision["paper_id"]
            check(pid in methods and (wid in methods[pid] or wid in extra_methods.get(pid, [])),
                  f"Invalid byline check: {pid} / {wid}")
            if by_person[pid].get(wid, "").startswith("manual_") and not decision["state"].startswith("manual_"):
                continue
            by_person[pid][wid] = decision["state"]
            links[pid, wid]["followup_byline"] = decision["state"]
        for row in batch.get("corrections", []):
            wid, tag = row["paper_id"], row["tag"]
            check(wid in queue and tag in tags and href(row["source"]), f"Invalid method correction: {row}")
            corrections[wid][tag] = row

    for wid, row in checks.items():
        works[wid]["followup_check"] = row
    for wid, tags_removed in corrections.items():
        works[wid]["method_corrections"] = list(tags_removed.values())
    evidence[:] = [row for row in [*evidence, *tested.values()]
                   if row["level"] == REVIEWED or row["tag"] not in corrections.get(row["paper_id"], {})]

    reviewed_people = {pid for pid, _, _, level in tested if level == REVIEWED}
    primary_people = {row["person_id"] for row in evidence if row["level"] == PRIMARY}
    publication_counts = Counter(pid for (pid, _), link in links.items() if "followup_batch" in link)
    rows = []
    for pid, papers in methods.items():
        complete = sum(wid in checks for wid in papers)
        row = {"person_id": pid, "cohort": "method_review", "papers_queued": len(papers),
               "papers_checked": complete, "byline_checks": Counter(by_person[pid].values()),
               "alternate_papers_checked": sum(wid in checks for wid in extra_methods.get(pid, [])),
               "state": ("source_reviewed" if pid in reviewed_people else
                         "primary_abstract" if pid in primary_people else
                         "sources_checked" if complete == len(papers) else
                         "in_progress" if complete else "pending")}
        rows.append(row)
        faculty[pid]["followup"] = row
    for pid in sorted(missing):
        search = searches.get(pid, {})
        row = {"person_id": pid, "cohort": "publication_search",
               "state": ("papers_found" if publication_counts[pid] else
                         search.get("state", "pending")), "papers_found": publication_counts[pid],
               "sources": search.get("sources", []), "checked_at": search.get("checked_at"),
               "batch": search.get("batch")}
        rows.append(row)
        faculty[pid]["followup"] = row
    return {
        "baseline": cohort["baseline"], "batches": batches,
        "method_cohort": len(methods), "publication_cohort": len(missing),
        "queued_works": len(original_queue), "works_checked": len(original_queue & checks.keys()),
        "alternate_works_checked": len(extra_queue & checks.keys()),
        "alternate_faculty_attempted": sum(any(wid in checks for wid in papers) for papers in extra_methods.values()),
        "paper_outcomes": Counter(row["state"] for row in checks.values()),
        "method_corrections": sum(len(rows) for rows in corrections.values()),
        "method_faculty_attempted": sum(any(wid in checks for wid in papers) for papers in methods.values()),
        "method_faculty_all_queued_papers_checked": sum(all(wid in checks for wid in papers) for papers in methods.values()),
        "method_faculty_with_manual_evidence": len(reviewed_people & set(methods)),
        "method_faculty_with_primary_abstract_only": len((primary_people - reviewed_people) & set(methods)),
        "publication_faculty_attempted": len(searches),
        "publication_faculty_with_papers": len(publication_counts),
        "publication_faculty_outcomes": Counter(row["state"] for row in rows if row["cohort"] == "publication_search"),
        "publication_links_found": sum(publication_counts.values()),
        "distinct_publications_found": len({wid for (_, wid), link in links.items() if "followup_batch" in link}),
        "publication_links_by_source": Counter(link["discovery_method"] for link in links.values()
                                               if "followup_batch" in link),
    }, rows + list(checks.values())
