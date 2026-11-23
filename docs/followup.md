# Paper and publication follow-up

The cohorts are pinned to the first release in [cohorts.json](../data/followup/cohorts.json). They contain 777 faculty with unresolved method or design leads and 469 profiles that had no listed paper. A second search within the first cohort checks alternate publications when the original leads leave a research method unresolved. The [live coverage report](https://zyx-dirtystar.github.io/marketing-faculty-atlas/#/coverage) shows completed source checks and usable evidence.

The [deeper review plan](../data/followup/deep-review-plan.json) pins the remaining 84 method profiles and 270 publication searches to the previous release. It records the known paper queue and checks public author manuscripts, methods sections, institutional repositories, research profiles and CVs.

## What counts as evidence

| Result | Review procedure |
| --- | --- |
| Source reviewed | Read the paper, author manuscript or study description and record the byline, method and relevant location. |
| Primary full-text evidence | Record an explicitly reported technique from a matched paper or accepted manuscript and give the relevant methods section or PDF page. A successful access check means the methods text was retrieved. An annotation additionally requires a usable method statement and verified authorship. |
| Primary abstract evidence | Match the DOI, title and byline or ORCID, then run explicit method rules on a publisher-deposited abstract, publisher page or openly posted manuscript. Each result includes a technique, sentence number, source and rule version. |
| Registry only | The bibliographic source was checked and insufficient primary text was available for a method annotation. |
| Abstract read with no explicit method | The available text did not establish a method under these rules. |
| Identity or source gap | The name, source or record requires further evidence. |

Method mentions in editorials, background citations or proposals need context. For example, the [Journal of Consumer Psychology editorial](https://myscp.onlinelibrary.wiley.com/toc/15327663/31/1) was removed as a laboratory lead, while [the Monash survey study](https://research.monash.edu/en/publications/a-simplified-approach-to-understanding-customer-support-and-help-/) supports latent-variable modeling. Controlled studies and live operational settings can be tagged on the same publication, as in [the Monash customer-name study](https://research.monash.edu/en/publications/call-me-by-my-name-the-effects-of-addressing-customers-by-their-n/).

## Publication search

The search uses upstream links to school profiles, personal sites, public CVs and publication pages, following additional links when appropriate. DOI and title matches require a concordant registered author. A secondary route identifies a unique indexed author from an already verified faculty profile, and links papers with the same recorded institution on their author entry or an exact ORCID. This secondary route is labeled separately in the authorship export. Some papers are outside Marketing and remain bibliographic records with their original titles and venues.

The follow-up export enumerates sources consulted and distinguishes published links, a readable profile with insufficient publication evidence, access failures and a profile whose identity needs review. These searches cover publicly accessible records at the recorded URLs and times. The maximum of 20 recent indexed records applies only to the supplemental affiliation search.

Deeper publication checks require that the DOI or citation comes from the listed institution or an independently confirmed author page. A matching name on a third-party index, an unrelated CV, or a standalone publication page cannot establish identity. DOI-free repository records require a byline and explicitly identified publication type.

The atlas also records a working paper when the work has a titled entry in a publicly posted university or author bibliography, a public CV, or a manuscript with verifiable authorship. CV-only entries link to the listing. A research-method label additionally requires an accessible study description or methods section for that paper.

## Rebuild and update

`python scripts/build.py` validates and applies each checked-in batch. The [data tables](https://zyx-dirtystar.github.io/marketing-faculty-atlas/#/coverage) are produced from the same merged data as the profile pages. Python collectors in [scripts](../scripts) use local JSONL caches. The profile reader and public paper reader use Beautiful Soup, and PDF text extraction uses `pdftotext` when available. Keep downloaded source text in the local cache. Source locations, bibliographic metadata, derived claims and access outcomes are the release artifacts.
