# Pilot and expansion audit

## Trial design

The initial source review covers 12 papers and 13 faculty. Selection deliberately spans quantitative Marketing and Consumer Behavior, with comparisons across structural demand, analytical modeling, advertising field experiments, online controlled experiments, laboratory work and machine learning. The five expansion checks extend manual review across two European and two Asian institutions. The [paper register](../data/pilot.json) contains every sampled DOI, author ID, source and rationale.

| Case | Decision |
| --- | --- |
| Dubé and Hitsch, brand choice and category pricing | Estimate behavioral parameters from household purchases. Two independent papers support recurring structural demand work. [State dependence](https://doi.org/10.1111/j.1756-2171.2010.00106.x) · [Category pricing](https://doi.org/10.1287/mksc.1070.0305) |
| Gordon and Zettelmeyer, Facebook ad benchmarks | Tag field experiments and causal measurement. The follow-up tests double/debiased ML with the randomized evidence as a benchmark. [First comparison](https://doi.org/10.1287/mksc.2018.1135) · [Follow-up](https://arxiv.org/abs/2201.07055) |
| Morozov and Tuchman, online bookstore | Code the simulated store as a controlled online experiment. The paper's lab keyword describes the experimental controls, and the recruitment and execution identify its online mode. [Paper](https://doi.org/10.1287/mksc.2023.0138) |
| Zhang and Raju, combative advertising | Code both the equilibrium model and laboratory evaluation. One paper can support multiple research methods. [Paper](https://doi.org/10.1287/mksc.1080.0385) |
| Fishbach and Woolley, immediate rewards | The exercise study gives behavioral field evidence. Studies within one article count as one work. [Author manuscript](https://kaitlinwoolleycom.files.wordpress.com/2017/08/woolleyfishbachjcr20161.pdf) |
| Berger and Milkman, virality | Keep historical press data and randomized story variants as different designs within the same work. [Author manuscript](https://jonahberger.com/wp-content/uploads/2013/02/ViralityB.pdf) |
| Jia and coauthors, slow-motion video | Source review confirms three designs in a single CB paper, with separate Facebook field, lab and online studies. [Paper](https://doi.org/10.1177/00222437211025054) |
| Cao and coauthors, creator selection | Two deep neural networks are part of a causal DiD method for heterogeneous effects. The rule-based DiD hit alone did not establish all the method labels. [Paper](https://doi.org/10.1287/mksc.2023.0511) |

## Errors and missing data

- The upstream profile for Z. John Zhang contains a paper credited to Jack H. Zhang. The paper remains visible as an upstream association requiring review and gives Z. John Zhang no tags. [Publisher record](https://doi.org/10.1177/01492063241247499)
- The category-pricing paper appears with a DOI on one faculty profile and without a DOI on another. Matching the complete title and byline links these records to the same work. The test requires two genuinely different papers for recurring structural demand estimation.
- Full bibliography coverage varies by school and source. We tested exact ORCID discovery for empty profiles where the directory provides an ORCID, and flagged records that remain empty. The build reports missing abstracts and questionable bylines separately.
- This purposive review diagnoses classification and data issues. It does not estimate accuracy over all faculty. The [live coverage report](https://zyx-dirtystar.github.io/marketing-faculty-atlas/download/coverage.json) gives the complete counts and breakdowns, including papers with limited access.
