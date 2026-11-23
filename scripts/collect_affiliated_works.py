"""Find papers for validated profiles by exact author name and institutional affiliation."""

import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlencode

from followup_http import Network, cache_rows, collect
from make_method_batch import exact_name
from sync import ROOT, load, orcid_key, title_key


def openalex(network, entity, params):
    if key := os.environ.get("OPENALEX_API_KEY"):
        params["api_key"] = key
    outcome, body = network.get(
        "https://api.openalex.org/" + entity + "?" + urlencode(params), "application/json")
    return outcome, json.loads(body).get("results", []) if body else []


def same_institution(school, institution):
    public_name = title_key(institution.get("display_name"))
    expected = {title_key(school["name"]), title_key(school["short"])} - {""}
    return bool(public_name and any(public_name == key for key in expected))


class AffiliationMatch:
    def __init__(self, faculty, schools, sources):
        self.faculty = faculty
        self.schools = schools
        self.sources = sources
        self.network = Network()

    def __call__(self, pid):
        person = self.faculty[pid]
        school = self.schools[person["school"]]
        profile = next(row["url"] for row in self.sources[pid]["sources"]
                       if row["status"] == "identity_checked")
        outcome, rows = openalex(self.network, "authors", {
            "search": person["name"], "per-page": 12,
            "select": "id,display_name,display_name_alternatives,orcid,affiliations,last_known_institutions",
        })
        if outcome["status"] != "read":
            return {"status": outcome["status"], "profile": profile}
        candidates = {}
        for row in rows:
            if not any(exact_name(person["name"], name)
                       for name in [row["display_name"], *(row["display_name_alternatives"] or [])]):
                continue
            affiliations = [item.get("institution") or {} for item in (row["affiliations"] or [])]
            institutions = {inst["id"] for inst in affiliations + (row["last_known_institutions"] or [])
                            if same_institution(school, inst)}
            exact_orcid = bool(orcid_key(person["orcid"]) and orcid_key(person["orcid"]) == orcid_key(row["orcid"]))
            if institutions or exact_orcid:
                candidates[row["id"]] = (sorted(institutions), exact_orcid)
        if len(candidates) != 1:
            return {"status": "no_unique_affiliation", "matches": len(candidates), "profile": profile}
        author, (institutions, exact_orcid) = next(iter(candidates.items()))
        outcome, rows = openalex(self.network, "works", {
            "filter": "author.id:" + author.rsplit("/", 1)[-1] + ",has_doi:true",
            "per-page": 20, "sort": "publication_date:desc",
            "select": "id,doi,title,authorships,abstract_inverted_index,is_retracted,publication_year,type,primary_location",
        })
        if outcome["status"] != "read":
            return {"status": outcome["status"], "profile": profile}
        found = []
        for row in rows:
            if row["is_retracted"] or not row["title"] or row["type"] not in {"article", "preprint", "working-paper"}:
                continue
            byline = [item for item in row["authorships"] if item["author"]["id"] == author]
            if len(byline) != 1:
                continue
            match = byline[0]
            actual = {inst["id"] for inst in match["institutions"]}
            if exact_orcid or set(institutions) & actual:
                found.append(row)
        return {"status": "affiliation_checked", "profile": profile, "author": author,
                "institution_ids": institutions, "exact_orcid": exact_orcid, "papers": found}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("faculty_sources", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--retry", action="store_true")
    args = parser.parse_args()
    people = load(ROOT / "data/faculty.json")
    schools = load(ROOT / "data/schools.json")
    sources = cache_rows(args.faculty_sources)
    keys = sorted(pid for pid, row in sources.items() if not row["dois"] and
                  any(item["status"] == "identity_checked" for item in row["sources"]))
    collect(keys, AffiliationMatch(people, schools, sources), args.output, workers=8, retry=args.retry)


if __name__ == "__main__":
    main()
