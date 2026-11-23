"""Recognize explicit study methods in primary-source abstracts."""

import re

VERSION = "primary-abstract-1.1"
ACTION = re.compile(r"\b(?:this (?:study|paper|research|article)|we|our (?:study|research|results|data)|"
                    r"the authors?|i (?:use|conduct|estimate|develop)|using|based on|with data from|"
                    r"evidence from|results from|(?:multiple|two|three|four|five|six|seven|eight|nine) studies|"
                    r"data (?:from|collected)|conducted|carried out|participants? (?:were|are)|"
                    r"was (?:conducted|tested)|are (?:reported|used)|was used)\b", re.I)
BACKGROUND = re.compile(r"\b(?:previous (?:research|studies)|prior (?:research|studies)|the literature|"
                        r"future research|has traditionally|in contrast to (?:prior|previous)|"
                        r"we do not (?:use|run|apply)|could be used|can be used to|for example)\b", re.I)

RULES = {
    "field": (r"\b(?:field|in.field) (?:experiments?|trials?)\b", "Field experiment"),
    "lab": (r"(?<!online )\b(?:laboratory|lab) (?:experiments?|stud(?:y|ies))\b|"
            r"\bcontrolled lab(?:oratory)? setting\b", "Laboratory experiment or controlled lab study"),
    "online": (r"\bonline (?:lab(?:oratory)?|vignette|survey) (?:experiments?|studies|study)\b|"
               r"\b(?:online|web.based) experiments?\b[^.;]{0,100}\b(?:participants?|respondents?|vignettes?|survey|"
               r"prolific|mechanical turk)\b", "Controlled online experiment"),
    "rct": (r"\b(?:randomi[sz]ed (?:controlled |field |cluster |lab(?:oratory)? )?(?:experiment|trial)s?|"
            r"randomly assign(?:ed|s)?|cluster randomi[sz]ation|randomi[sz]ed assignment)\b", "Randomized assignment"),
    "structural": (r"\bstructurally estimat\w+|\b(?:estimat\w+|calibrat\w+|fit)\b[^.;]{0,95}\bstructural "
                   r"(?:model|demand|supply|game)", "Structural model estimated or calibrated"),
    "demand_estimation": (r"\b(?:estimat\w+|calibrat\w+|fit)\b[^.;]{0,105}\b(?:structural (?:demand model|"
                          r"model of (?:consumer )?demand)|random.coefficients (?:demand|discrete.choice))",
                          "Structural demand estimation"),
    "analytical": (r"\b(?:model|framework|approach)\b[^.;]{0,70}\b(?:Nash |subgame.perfect )equilibr\w+|"
                   r"\b(?:game.theoretic(?:al)?|duopoly|oligopoly|analytical) model\b|"
                   r"\b(?:derive|characterize)\w*\b[^.;]{0,65}\b(?:equilibrium|equilibria)\b",
                   "Formal equilibrium or analytical model"),
    "behavioral_theory": (r"\b(?:propose|introduce|develop)\w*\b[^.;]{0,75}\b(?:conceptual framework|"
                          r"conceptual model|a theory of (?:consumer|motivation|goal pursuit|self.regulation))",
                          "Conceptual model or behavioral theory"),
    "ml": (r"\b(?:machine.learning|deep learning|gradient boost\w+|causal forests?|random forests?|"
           r"neural networks?|support vector machines?|large language models?|transformer.based model)\b",
           "Machine learning algorithm"),
    "causal_ml": (r"\b(?:double(?:/debiased|[- ]debiased)?|debiased) machine learning\b|\bcausal forests?\b|"
                  r"\b(?:neural networks?|machine learning)\b[^.;]{0,100}\b(?:heterogeneous|conditional average)"
                  r" treatment effects?\b", "Machine learning for treatment-effect estimation"),
    "nlp": (r"\b(?:natural language processing|text classifi\w+|topic model\w*|word embeddings?)\b",
            "Computational text analysis"),
    "computer_vision": (r"\b(?:computer vision|image classification|visual recognition|vision.language models?)\b",
                        "Computer vision"),
    "reduced_form": (r"\breduced.form (?:estimators?|estimation|regressions?|econometric\w*|approach|models?)\b",
                     "Reduced-form econometric analysis"),
    "behavioral_experiment": (r"\bparticipants?\b[^.;]{0,70}\brandomly assigned\b|"
                              r"\b(?:behavioral|laboratory|lab) experiments?\b|"
                              r"\b(?:experimental studies|controlled experiments?)\b[^.;]{0,110}\b"
                              r"(?:consumers?|participants?|purchase intentions?|consumer behavior)\b",
                              "Behavioral experiment"),
    "qualitative": (r"\b(?:semi.structured interviews?|ethnograph\w+|grounded theory coding|qualitative interviews?)\b",
                    "Qualitative data collection or analysis"),
    "mixed_methods": (r"\bmixed.methods? (?:design|study|research|approach|analysis)\b", "Mixed-methods design"),
    "meta_analysis": (r"\bmeta.analys(?:is|es|tic)\b", "Meta-analysis"),
    "conjoint": (r"\b(?:choice.based conjoint|conjoint (?:analysis|task|design|study))\b", "Conjoint analysis"),
    "sem": (r"\b(?:structural equation modell?ing|structural equation model|latent variable modell?ing)\b",
            "Structural equation or latent-variable modeling"),
    "bayesian": (r"\b(?:hierarchical Bayesian|Bayesian hierarchical) (?:model|method|framework|approach)\b",
                 "Hierarchical Bayesian estimation"),
    "observational": (r"\b(?:observational (?:data|records)|scanner (?:data|panel)|"
                      r"(?:sales|transaction|household purchase) (?:data|records|panel))\b", "Observed records or panel data"),
    "quasi": (r"\b(?:natural experiment|quasi.experiment\w*|exogenous shock)\b", "Quasi-experimental variation"),
    "did": (r"\bdifference[s]?[- –]in[- –]difference[s]?\b", "Difference-in-differences"),
    "rd": (r"\bregression[- ]discontinuity\b", "Regression discontinuity"),
    "iv": (r"\b(?:instrumental variables? (?:approach|estimator|strategy|design|regression)|"
           r"using (?:an? |the )?instrumental variables?|two.stage least squares)\b", "Instrumental variables"),
    "sc": (r"\bsynthetic control(?:s| group| method| estimator| approach)?\b", "Synthetic control"),
    "descriptive": (r"\b(?:document|characteri[sz]e)\w*\b[^.;]{0,75}\b(?:patterns|correlations|trends)\b",
                    "Descriptive patterns or correlations"),
    "predictive": (r"\b(?:out.of.sample (?:prediction|forecasting)|prediction (?:accuracy|performance)|"
                   r"forecast accuracy|predictive performance)\b", "Out-of-sample prediction or predictive accuracy"),
    "counterfactual": (r"\b(?:counterfactual (?:simulations?|analys[ie]s|experiments?)|simulate\w* counterfactual)\b",
                       "Model-based counterfactual analysis"),
    "causal": (r"\b(?:estimat\w*|identif\w*|measur\w*|recover\w*)\b[^.;]{0,70}"
               r"\b(?:causal (?:effects?|impact)|(?:heterogeneous |average )?treatment effects?)\b",
               "Treatment-effect estimation"),
}

VARIANTS = {
    "rct": [(r"cluster randomi[sz]\w+", "cluster randomization"),
            (r"randomi[sz]ed controlled trial", "randomized controlled trial"),
            (r"randomi[sz]ed field experiment", "randomized field experiment")],
    "did": [(r"synthetic difference", "synthetic DiD"), (r"staggered", "staggered adoption")],
    "rd": [(r"fuzzy regression", "fuzzy RD"), (r"sharp regression", "sharp RD")],
    "iv": [(r"two.stage least squares", "two-stage least squares")],
    "structural": [(r"dynamic discrete choice", "dynamic discrete choice"),
                   (r"random.coefficients", "random coefficients")],
    "ml": [(r"random forests?", "random forest"), (r"gradient boost\w+", "gradient boosting"),
           (r"neural networks?", "neural network"), (r"deep learning", "deep learning"),
           (r"support vector machines?", "support vector machine"),
           (r"large language models?", "large language model")],
    "causal_ml": [(r"causal forests?", "causal forest"),
                  (r"(?:double(?:/debiased|[- ]debiased)?|debiased) machine learning", "double/debiased machine learning")],
    "field": [(r"field experiments?\b[^.;]{0,75}\b(?:facebook|wechat|linkedin|ebay|airbnb)\b", "live platform"),
              (r"field experiments?\b[^.;]{0,75}\b(?:retail store|supermarket)\b", "retail setting")],
}

PARENTS = {"demand_estimation": ("structural", "empirical"), "causal_ml": ("ml", "causal"),
           "did": ("quasi", "causal", "empirical"), "rd": ("quasi", "causal", "empirical"),
           "iv": ("causal", "empirical"), "sc": ("quasi", "causal", "empirical"),
           **{tag: ("empirical",) for tag in ("rct", "field", "lab", "online", "structural", "observational", "quasi")}}

STUDY_CONTEXT = re.compile(r"\b(?:results?|show\w*|report\w*|test\w*|demonstrat\w*|reveal\w*|analy[sz]\w*|"
                           r"collected|implement\w*|consist\w*|identif\w*|examin\w*|compar\w*|"
                           r"uncover\w*|provide\w* (?:support|evidence))\b", re.I)
ML_CONTEXT = re.compile(r"\b(?:use\w*|apply|develop\w*|fit\w*|employ\w*|implement\w*|train\w*|"
                        r"algorithm|model|approach|predict\w*|estimat\w*)\b", re.I)
ML_SUBJECT = re.compile(r"\b(?:effect|perception|adoption|attitudes?|trust|impact)\b[^.;]{0,30}"
                        r"\b(?:of|toward|towards)\b[^.;]{0,28}"
                        r"\b(?:AI|machine.learning|large language models?)\b", re.I)
ECONOMIC_STRUCTURE = re.compile(r"\b(?:demand|supply|differentiated products|discrete choice|game|welfare|"
                               r"pricing|preferences?|counterfactual|utility|equilibrium|consumer search)\b", re.I)


def extract(abstract):
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9“])", abstract)
    hits = {}
    for position, sentence in enumerate(sentences, 1):
        for tag, (pattern, technique) in RULES.items():
            if tag in hits or not re.search(pattern, sentence, re.I):
                continue
            if BACKGROUND.search(sentence) and not re.search(r"\b(?:we (?:use|run|apply|conduct|estimate)|this study applies)\b",
                                                             sentence, re.I):
                continue
            if not ACTION.search(sentence) and not STUDY_CONTEXT.search(sentence):
                continue
            if tag in {"ml", "nlp", "computer_vision"} and (
                    not ML_CONTEXT.search(sentence) or ML_SUBJECT.search(sentence)):
                continue
            if tag == "structural" and (not ECONOMIC_STRUCTURE.search(sentence) or
                                        re.search(r"\bstructural equation model", sentence, re.I)):
                continue
            specific = next((value for expr, value in VARIANTS.get(tag, []) if re.search(expr, sentence, re.I)), "")
            hits[tag] = {"tag": tag, "sentence": position, "technique": specific or technique,
                         "rule": VERSION, "note": f"The study abstract identifies {specific or technique}."}
    for tag, evidence in list(hits.items()):
        for broader in PARENTS.get(tag, ()):
            hits.setdefault(broader, {**evidence, "tag": broader, "derived_from": tag})
    return list(hits.values())
