"""Find publicly listed works for ORCIDs attached to verified faculty profiles."""

import argparse
import json
from pathlib import Path

from followup_http import Network, collect
from sync import ROOT, load, orcid_key

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--profiles", type=Path)
    args = parser.parse_args()
    faculty = load(ROOT / "data/faculty.json")
    pinned = load(ROOT / "data/followup/deep-review-plan.json")["publication_search"]
    supplied = load(args.profiles) if args.profiles else {}
    ids = {pid: orcid_key(faculty[pid]["orcid"]) or orcid_key(supplied.get(pid, {}).get("orcid"))
           for pid in pinned}
    network = Network()

    def lookup(pid):
        identifier = ids[pid].split("/")[-1]
        public = "https://orcid.org/" + identifier
        profile = supplied.get(pid, {}).get("source") or faculty[pid]["links"].get("profile_url") or public
        state, raw = network.get("https://pub.orcid.org/v3.0/" + identifier + "/works",
                                 "application/vnd.orcid+json")
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
