"""Search for papers with a publisher-registered faculty name and business affiliation."""

import argparse
import json
from pathlib import Path
import re
from urllib.parse import urlencode

from followup_http import Network, collect
from make_method_batch import record_names
from sync import ROOT, load, title_key, words

BUSINESS_UNIT = re.compile(
    r"\b(?:marketing|management|business|commerce|economics|retail|tourism|hospitality|"
    r"administrative sciences|administration des affaires|economie|gestion)\b", re.I)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("followup", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--aliases", type=Path)
    parser.add_argument("--retry", action="store_true")
    args = parser.parse_args()
    plan = load(ROOT / "data/followup/deep-review-plan.json")
    faculty = load(ROOT / "data/faculty.json")
    schools = load(ROOT / "data/schools.json")
    aliases = load(args.aliases) if args.aliases else {}
    missing = {entry["person_id"] for entry in load(args.followup)
               if entry.get("cohort") == "publication_search" and entry["state"] != "papers_found"}
    network = Network()

    def get(pid):
        person = faculty[pid]
        school = schools[person["school"]]
        names = [re.sub(r"^(?:Dr|Prof)\.?\s+", "", name, flags=re.I)
                 for name in [person["name"], *aliases.get(pid, [])]]
        accepted = {tuple(words(name)) for name in names if len(words(name)) >= 2}
        institution = title_key(school["name"])
        short = title_key(school.get("short"))
        institutions = {institution, short} - {""}
        institutions = {name for name in institutions if len(name) >= 7 and
                        (name == institution or name.endswith(("university", "school", "college")))}
        if not accepted:
            return {"status": "incomplete_roster_name",
                    "source": person["links"].get("profile_url") or person["upstream_url"], "works": []}
        params = {"query.author": max(names, key=len), "query.affiliation": school["name"],
                  "filter": "type:journal-article", "rows": 20,
                  "select": "DOI,title,author,published,container-title,type,URL,update-to"}
        query = "https://api.crossref.org/works?" + urlencode(params)
        outcome, body = network.get(query, "application/json", limit=3_000_000)
        works = []
        for row in json.loads(body)["message"]["items"] if body else []:
            for name, author in zip(record_names(row), row.get("author", [])):
                if tuple(words(name)) not in accepted:
                    continue
                for affiliation in author.get("affiliation", []):
                    raw = affiliation.get("name") or ""
                    if BUSINESS_UNIT.search(raw) and any(inst in title_key(raw) for inst in institutions):
                        works.append({"work": row, "affiliation": raw})
                        break
                else:
                    continue
                break
        return {"status": outcome["status"], "source": query, "works": works}

    collect([pid for pid in plan["publication_search"] if pid in missing], get, args.output,
            workers=8, retry=args.retry)


if __name__ == "__main__":
    main()
