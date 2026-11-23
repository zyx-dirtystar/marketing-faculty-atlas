# Classification and data dictionary

## Paper classifications

Each paper can have multiple labels within or across dimensions. The [taxonomy](../data/taxonomy.json) defines stable IDs and the labels shown on the site.

| Dimension | Decision rule |
| --- | --- |
| Research topic | The substantive problem, such as pricing, brand loyalty, search, targeted advertising or motivation. |
| Structural estimation | Estimate or calibrate a model with interpretable economic or behavioral parameters using data. Structural demand estimation is a specialization. |
| Analytical modeling / game theory | Derive results from a formal model, such as equilibrium pricing or strategic competition. A paper with a formal model and a laboratory test can receive both labels. |
| Behavioral / conceptual theory | Develop a behavioral theory or substantive conceptual framework. |
| Machine learning | Apply or develop a learning algorithm as part of the analysis. Causal ML includes applications such as double/debiased ML or causal forests that target a causal estimand. Studying adoption or perceptions of AI supports a topic label. |
| Reduced-form econometrics | Estimate relationships or effects without a full model of the underlying choices. Record the identifying variation when available. |
| Behavioral experiments and qualitative methods | Record what participants experience or how interviews, ethnography, coding or mixed methods are used. |
| Empirical objective | Distinguish description, prediction, causal inference, and model-based counterfactuals. |
| Design and identification | Field research uses a live setting with real behavior. Laboratory and online controlled settings include scripted tasks. A real platform can host a field experiment. Record randomized assignment, DiD, IV, regression discontinuity or synthetic control only where the design supports the claim. |

A source-reviewed tag describes what the paper does. For causal inference it can describe a causal method under evaluation, including a method that fails to recover experimental effects. A coauthorship establishes participation in the work. The published evidence does not assign individual contributions to the method.

## Evidence and identity

- **Source reviewed** links to a publisher abstract, an author manuscript or a method section. The review register declares which authors were checked against that source. Within the participant's reviewed paper, reviewed tags take precedence over automatic suggestions.
- **Abstract signal** means a versioned search rule found a phrase in a DOI-matched OpenAlex abstract or a topic term in the title of an article with an indexed abstract. The record gives the source, location and token range. Abstract mentions can describe cited work, failed methods or proposed future work. A hit is a lead for review.
- **Authorship needs review** flags upstream bylines that fail the name check against the profile or whose OpenAlex byline differs. Source review can resolve documented variants. The full record is retained for correction. Exact ORCID discovery requires both an ORCID match and a concordant name, and caps the search at the most recent 18 DOI works returned before type filtering.
- Faculty coverage distinguishes source-reviewed, abstract signals, abstracts with no signal, candidate works with unavailable abstracts, disputed authorships, and no listed works. Counts describe the inspected corpus. The project prioritizes precision and may miss methods whose names appear only in full text.
- Confirmed recurring tags need two distinct source-reviewed works. The directory's **At least two papers** filter uses the evidence level selected by the reader. **Same paper** applies all chosen tags jointly to each matching paper.
- DOI is the work key when available. An exact normalized title and byline resolve DOI-less copies only when they point to one DOI. Other known publication and preprint versions are joined through review aliases. Distinct versions and original source statuses stay in the work and authorship records. Changes in title or byline can leave versions requiring manual reconciliation.

## Published tables

| Table | Keys and fields |
| --- | --- |
| Faculty | Econ Atlas faculty ID, school ID, appointment and education fields, original field labels, the source paper count, and the reviewed and abstract-signal tag counts. |
| Papers | Stable DOI-based or title/byline-based ID, title, byline, DOI, venue, year, status, source versions, discovery provider, abstract availability and known retraction status. |
| Authorships | Faculty ID and work ID, original upstream paper statuses and authorship confidence. |
| Evidence | Work ID and tag, evidence level, source URL, location and explanation. Reviewed rows include the source-check date. Rule hits include the rule version and zero-based token range. To recover a faculty's reviewed tags using exports, join only authorships with `identity=source_reviewed`. |
| Coverage | Source commits, retrieved DOI count, abstract availability, roster comparison, and breakdowns by scope, original Marketing field and institution. Marketing field totals can overlap. |

In placement cross-checks, shared URLs or ORCIDs are paired with a concordant name. The old identity reconciliation file supplies additional URLs and its taxonomy supplies track aliases. Name-only matches stay available for review. Institution display-name differences include aliases and potential appointment changes. The old project's snapshot dates and underlying links remain visible for adjudication.
