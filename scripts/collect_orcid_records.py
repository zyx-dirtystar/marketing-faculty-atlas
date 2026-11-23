"""Find publicly listed works for ORCIDs attached to verified faculty profiles."""

import argparse
import json
from pathlib import Path

from followup_http import Network, collect
from make_method_batch import exact_name
from sync import ROOT, load, orcid_key

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--profiles", type=Path)
    parser.add_argument("--aliases", type=Path)
    args = parser.parse_args()
    faculty = load(ROOT / "data/faculty.json")
    pinned = load(ROOT / "data/followup/deep-review-plan.json")["publication_search"]
    supplied = load(args.profiles) if args.profiles else {}
    aliases = load(args.aliases) if args.aliases else {}
    ids = {pid: orcid_key(faculty[pid]["orcid"]) or orcid_key(supplied.get(pid, {}).get("orcid"))
           for pid in pinned}
    network = Network()

    def lookup(pid):
        identifier = ids[pid].split("/")[-1]
        public = "https://orcid.org/" + identifier
        profile = supplied.get(pid, {}).get("source") or faculty[pid]["links"].get("profile_url") or public
        api = "https://pub.orcid.org/v3.0/" + identifier
        state, raw = network.get(api + "/person", "application/vnd.orcid+json")
        person = json.loads(raw) if raw else {}
        name = person.get("name") or {}
        byline = " ".join((name.get(field) or {}).get("value", "") for field in ("given-names", "family-name"))
        registry_names = [byline, (name.get("credit-name") or {}).get("value", "")]
        registry_names.extend(row.get("content", "") for row in (person.get("other-names") or {}).get("other-name", []))
        expected = [faculty[pid]["name"], *aliases.get(pid, [])]
        if not any(exact_name(candidate, actual) for candidate in expected for actual in registry_names):
            status = "orcid_name_mismatch" if byline.strip() else "orcid_name_unavailable" if raw else state["status"]
            return {"status": status, "dois": {}, "sources": [
                {"url": public, "role": "orcid_public_profile", "status": status, "citations": []}]}
        state, raw = network.get(api + "/works", "application/vnd.orcid+json")
        dois = {}
        for group in json.loads(raw).get("group", []) if raw else []:
            for work in group.get("work-summary", []):
                if work.get("type") not in {"journal-article", "working-paper", "preprint", "conference-paper"}:
                    continue
                for external in work.get("external-ids", {}).get("external-id", []):
                    if (external["external-id-type"].lower() == "doi" and
                            external.get("external-id-relationship") == "self"):
                        doi = external["external-id-value"].lower().removeprefix("https://doi.org/")
                        if doi.startswith("10."):
                            dois[doi] = [public]
        return {"status": state["status"], "dois": dois, "sources": [
            {"url": profile, "status": "identity_checked", "role": "orcid_profile_reference", "citations": []},
            {"url": public, "status": "identity_checked" if raw else state["status"],
             "role": "orcid_public_works", "citations": []}]}

    collect([pid for pid, identifier in ids.items() if identifier], lookup, args.output, workers=6)


if __name__ == "__main__":
    main()
