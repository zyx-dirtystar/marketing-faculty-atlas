"""Conservative, auditable first-pass rules over DOI-matched abstracts."""

import re

VERSION = "abstract-rules-1.0"

# These are search signals. A rule hit queues a review and never grants verification.
RULES = {
    "structural": [
        r"\bstructurally estimat\w+",
        r"\b(?:estimate|estimating|fit|calibrat\w+)\b[^.!?]{0,90}\b(?:a |the )?structural (?:model|demand|supply|game)",
    ],
    "demand_estimation": [
        r"\b(?:estimate|estimating|fit|calibrat\w+)\b[^.!?]{0,90}\bstructural (?:model of (?:consumer )?demand|demand model)",
    ],
    "analytical": [
        r"\b(?:we|this paper) (?:develop\w*|formulate\w*|analy[sz]\w*|study|build\w*)\b[^.!?]{0,95}\b(?:game-theoretic(?:al)?|analytica?l|duopoly|oligopoly) model",
        r"\bderive\w*\b[^.!?]{0,60}\b(?:equilibrium pricing|equilibrium strategies|Nash equilibria)",
    ],
    "behavioral_theory": [
        r"\b(?:we|this article) (?:propose\w*|develop\w*|introduce\w*)\b[^.!?]{0,80}\b(?:conceptual framework|conceptual model|theory of (?:consumer|motivation|self-regulation))",
    ],
    "ml": [
        r"\b(?:we|the proposed approach|our model) (?:use\w*|apply|employ\w*|develop\w*|train\w*|implement\w*|compar\w*)\b[^.!?]{0,110}\b(?:machine[- ]learning|deep learning|neural networks?|random forests?|gradient boosting|support vector machines?|large language models?|causal forests?)",
        r"\b(?:using|trained using|implemented with) (?:a |an |the )?(?:machine[- ]learning|deep learning|random forests?|neural networks?|gradient boosting|large language models?|causal forests?)",
        r"\b(?:double(?:/debiased|[- ]debiased)?|debiased) machine learning\b",
    ],
    "causal_ml": [
        r"\b(?:double(?:/debiased|[- ]debiased)?|debiased) machine learning\b",
        r"\bcausal forests?\b",
        r"\b(?:using|apply|employ\w*)\b[^.!?]{0,50}\bmachine learning\b[^.!?]{0,65}\b(?:heterogeneous|conditional average) treatment effects?\b",
    ],
    "nlp": [r"\b(?:use\w*|apply|applying|employ\w*)\b[^.!?]{0,90}\b(?:natural language processing|topic model\w*|word embeddings?)"],
    "computer_vision": [r"\b(?:use\w*|apply|applying|employ\w*|develop\w*|implement\w*)\b[^.!?]{0,90}\b(?:computer vision|image recognition|vision-language model)"],
    "reduced_form": [r"\b(?:we (?:use|implement|estimate|apply)|using)\b[^.!?]{0,65}\breduced[- ]form\b"],
    "behavioral_experiment": [
        r"\b(?:we|the authors) (?:conduct\w*|run|ran|report\w*|perform\w*)\b[^.!?]{0,65}\b(?:behavioral|laboratory|lab) experiments?",
        r"\bparticipants (?:were |are )?randomly assigned\b",
    ],
    "qualitative": [r"\b(?:we (?:conduct\w*|use\w*|draw on)|using)\b[^.!?]{0,55}\b(?:semi[- ]structured interviews?|ethnograph\w+|grounded theory|qualitative interviews?)"],
    "mixed_methods": [r"\b(?:use\w*|using|employ\w*|adopt\w*)\b[^.!?]{0,45}\bmixed[- ]methods?\b"],
    "meta_analysis": [r"\b(?:we (?:conduct\w*|perform\w*|report\w*)|using)\b[^.!?]{0,35}\bmeta[- ]analys[ie]s\b"],
    "field": [
        r"\b(?:field experiment\w*|field trials?)\b",
        r"\b(?:A/B test\w*)\b[^.!?]{0,60}\b(?:live|platform|customers?|advertisers?)\b",
    ],
    "lab": [r"\b(?:laboratory|lab) (?:experiment|studies|study)\w*\b"],
    "online": [
        r"\b(?:online (?:survey|vignette) experiment|online laboratory experiment)\w*\b",
        r"\b(?:vignette experiment|survey experiment)\w*\b[^.!?]{0,75}\b(?:online|Mechanical Turk|Prolific)\b",
    ],
    "observational": [
        r"\b(?:we (?:use|analy[sz]e|collect)|using)\b[^.!?]{0,70}\b(?:observational (?:data|records)|scanner (?:data|panel)|transaction (?:data|records))\b",
    ],
    "quasi": [r"\b(?:we (?:exploit|use|leverag\w+)|using)\b[^.!?]{0,65}\b(?:natural experiment|quasi[- ]experiment\w*|exogenous shock)\b"],
    "rct": [r"\b(?:randomi[sz]ed (?:controlled |field )?(?:trials?|experiments?|assignment)|randomly assign\w*)\b"],
    "did": [r"\bdifference[s]?[- ]in[- ]difference[s]?\b"],
    "iv": [r"\b(?:using|use|employ|implement|apply)\b[^.!?]{0,40}\binstrumental variables?\b"],
    "rd": [r"\bregression[- ]discontinuity\b"],
    "sc": [r"\b(?:use|using|employ\w*|apply)\b[^.!?]{0,40}\bsynthetic control\b"],
    "descriptive": [r"\b(?:we document|we characterize)\b[^.!?]{0,85}\b(?:patterns|correlations|descriptive|trends)\b"],
    "predictive": [r"\b(?:out-of-sample prediction|predictive accuracy|prediction performance|forecast accuracy)\b"],
    "causal": [
        r"\b(?:estimat\w*|identif\w*|measur\w*|recover\w*)\b[^.!?]{0,70}\b(?:causal effects?|treatment effects?|causal impact)\b",
    ],
    "counterfactual": [r"\b(?:counterfactual (?:simulations?|analys[ie]s|experiments?)|simulate\w* counterfactual)\b"],
}

TOPICS = {
    "pricing": r"\b(?:pricing|price elasticit\w+|price discrimination|price competition|price promotions?)\b",
    "advertising": r"\b(?:advertis\w+|ad campaigns?|ad effectiveness)\b",
    "platforms": r"\b(?:two-sided markets?|digital platforms?|online platforms?|online marketplaces?|platform competition)\b",
    "retail": r"\b(?:retail\w*|distribution channels?|omnichannel|supermarkets?)\b",
    "brands": r"\b(?:brand\w*|loyalty programs?)\b",
    "choice": r"\b(?:consumer choices?|consumer preferences?|brand choices?|purchase intentions?)\b",
    "search": r"\b(?:consumer search|search costs?|product search|sequential search)\b",
    "information": r"\b(?:information disclosure|information transparency|product disclosure)\b",
    "ai": r"\b(?:generative AI|artificial intelligence|chatbots?)\b",
    "sharing": r"\b(?:word of mouth|word-of-mouth|virality|content sharing|social sharing)\b",
    "motivation": r"\b(?:goal pursuit|long-term goals?|self-regulation|intrinsic motivation)\b",
    "targeting": r"\b(?:personali[sz]ation|personalized pricing|targeted advertising|behavioral targeting)\b",
    "welfare": r"\b(?:consumer welfare|public policy|consumer surplus|social welfare)\b",
}

RULES = {tag: [re.compile(pattern, re.I) for pattern in patterns]
         for tag, patterns in RULES.items()}
TOPICS = {tag: re.compile(pattern, re.I) for tag, pattern in TOPICS.items()}

IMPLIES = {
    "demand_estimation": ("structural",),
    "causal_ml": ("ml",),
    "structural": ("empirical",),
    "field": ("empirical",),
    "lab": ("empirical",),
    "online": ("empirical",),
    "observational": ("empirical",),
    "quasi": ("empirical",),
    "rct": ("empirical",),
    "did": ("quasi", "causal", "empirical"),
    "iv": ("causal", "empirical"),
    "rd": ("quasi", "causal", "empirical"),
    "sc": ("quasi", "causal", "empirical"),
}


def signals(title, abstract, source):
    hits = {}

    def record(tag, match, locator, reason):
        hits[tag] = {"tag": tag, "level": "abstract_signal", "source": source,
                     "locator": locator, "note": reason, "rule": VERSION,
                     "token_range": [len(match.string[:match.start()].split()),
                                     len(match.string[:match.end()].split())]}

    for tag, rules in RULES.items():
        for rule in rules:
            if match := rule.search(abstract):
                record(tag, match, "OpenAlex-indexed abstract",
                       "The abstract matches the method or design rule. Review its context before use.")
                break
    for tag, rule in TOPICS.items():
        if match := rule.search(title):
            record(tag, match, "Paper title", "The title contains a matching research topic.")
        elif match := rule.search(abstract):
            record(tag, match, "OpenAlex-indexed abstract", "The abstract contains a matching research topic.")
    for tag, hit in list(hits.items()):
        for parent in IMPLIES.get(tag, ()):
            if parent not in hits:
                hits[parent] = {**hit, "tag": parent, "derived_from": tag}
    return list(hits.values())
