"""Read the bibliographic record and any deposited abstract for all review DOIs."""

import argparse
from pathlib import Path

from followup_http import Network, collect
from sync import ROOT, load


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cache", type=Path)
    parser.add_argument("--retry", action="store_true")
    args = parser.parse_args()
    cohort = load(ROOT / "data/followup/cohorts.json")
    keys = [key.removeprefix("doi:") for key in cohort["paper_queue"] if key.startswith("doi:")]
    collect(keys, Network().crossref, args.cache, workers=8, retry=args.retry)


if __name__ == "__main__":
    main()
