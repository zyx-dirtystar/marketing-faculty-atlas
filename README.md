# Marketing Faculty Atlas

Research directory for Marketing faculty in Econ Atlas. Search by research topic, method, study design or identification strategy and follow the evidence to individual papers.

[Faculty directory](https://zyx-dirtystar.github.io/marketing-faculty-atlas/) · [Coverage and downloads](https://zyx-dirtystar.github.io/marketing-faculty-atlas/#/coverage) · [Classification and data dictionary](docs/methodology.md) · [Pilot and expansion audit](docs/pilot-audit.md)

## Data and scope

The default view reproduces the Econ Atlas Business School and Marketing filters. **All Marketing faculty** also includes Economics, agricultural and resource economics, and public policy faculty with an upstream Marketing field. The source snapshot and live-index comparison are recorded in [data/metadata.json](data/metadata.json). [Econ Atlas filter](https://econ-faculty.github.io/#/?ut=1&field=g%3AMarketing)

Each source-reviewed tag has a paper, a specific evidence description, and a reference to the study or publisher. Abstract signals are machine-generated leads. The profile shows how many distinct works support each tag and keeps coverage gaps visible. The website and CSV / JSON exports use the same data.

## Build locally

Python 3.12+ and Node.js 22+ suffice.

```sh
python scripts/build.py
npm test
python -m http.server 8000 -d dist
```

Open [localhost:8000](http://localhost:8000/). The GitHub Actions workflow builds, checks and deploys the same static output.

## Refresh the data

Use separate checkouts of [Econ Atlas](https://github.com/econ-faculty/econ-faculty.github.io) and [mkt-io-placement](https://github.com/zyx-dirtystar/mkt-io-placement). Check out the exact commits in the metadata to reconstruct the release. Use checked-in artifacts when available. For a new release, capture the live Econ Atlas `data.js` and reconcile changes in its faculty IDs and scope before publication.

```sh
python scripts/fetch_abstracts.py ../econ-atlas .cache/openalex.jsonl
python scripts/sync.py --upstream ../econ-atlas --placement ../mkt-io-placement --abstracts .cache/openalex.jsonl --live-index .cache/live-data.js --checked-at 2026-11-23
python scripts/discover_orcid.py .cache/orcid.json
python scripts/sync.py --upstream ../econ-atlas --placement ../mkt-io-placement --abstracts .cache/openalex.jsonl --orcid-discovery .cache/orcid.json --live-index .cache/live-data.js --checked-at 2026-11-23
python scripts/build.py
npm test
```

Use the new observation date when refreshing. Abstract accession and ORCID calls use OpenAlex public API access or an optional `OPENALEX_API_KEY` environment variable. The local cache saves responses between runs. Commit the generated JSON snapshot and review changes to the coverage report. The checked-in snapshot supports reproducible deployment while the external abstract index continues to evolve.

Edit the reviewer-maintained [paper register](data/pilot.json) to add or correct a paper-level claim, establish a version alias, or verify another faculty byline. The register is applied during sync and remains separate from the generated snapshot. To report a correction, open an issue with the faculty profile, DOI and evidence.

Follow-up reviews and publication searches are maintained in [data/followup](data/followup). The static build validates and applies each batch without modifying the upstream snapshot. Source collectors use local caches and the build runs from committed data alone.

## Attribution

Econ Atlas supplies the roster and original publication links. The Atlas retains its static Python build pattern and school-sharded profile layout using independently authored code. Publisher pages and author manuscripts supply the reviewed evidence. OpenAlex supplies DOI and exact-ORCID discovery metadata. The snapshot publishes bibliographic fields, original field labels, links and derived evidence summaries. Full abstracts and article PDFs stay with their sources. The placement project is used for cross-checks. [Econ Atlas source](https://github.com/econ-faculty/econ-faculty.github.io) · [OpenAlex](https://openalex.org/) · [mkt-io-placement](https://github.com/zyx-dirtystar/mkt-io-placement)
