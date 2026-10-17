"""Genetic markers (SIMULATED in this prototype): interpretation, kidney-risk modifier, drug cautions.

All cut-offs, odds ratios, wording and sources live in clinical_rules.yaml -> genetics.
- summarize(latest)        -> list of markers with a plain interpretation (for the doctor view, PDF, AI)
- dkd_odds_ratio(prs)      -> multiplier on the odds of the 3-year DKD outcome
- drug_cautions(genetics)  -> {"sulfonylurea": [...], "metformin": [...]} pharmacogenomic cautions
"""

from __future__ import annotations

from src.clinical.rules import clinical_rules

GENE_VARS = ["ckd_prs_percentile", "tcf7l2_rs7903146", "cyp2c9_phenotype", "slc22a1_reduced_alleles"]
_RULE_KEY = {"ckd_prs_percentile": "ckd_prs", "tcf7l2_rs7903146": "tcf7l2_rs7903146",
             "cyp2c9_phenotype": "cyp2c9_phenotype", "slc22a1_reduced_alleles": "slc22a1_reduced_alleles"}


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _interpret(var: str, v: float) -> tuple[str, bool]:
    """(plain-English result, is it a flag)."""
    g = clinical_rules()["genetics"]
    if var == "ckd_prs_percentile":
        r = g["ckd_prs"]
        if v >= r["high_from_percentile"]:
            return f"{_ordinal(round(v))} percentile: higher inherited kidney risk", True
        if v < r["low_below_percentile"]:
            return f"{_ordinal(round(v))} percentile: lower inherited kidney risk", False
        return f"{_ordinal(round(v))} percentile: average", False
    if var == "cyp2c9_phenotype":
        r = g["cyp2c9_phenotype"]
        name = r["values"].get(int(v), str(v))
        return f"{name} metaboliser", int(v) >= r["caution_from"]
    r = g[_RULE_KEY[var]]
    n = int(v)
    return f"{n} risk allele{'s' if n != 1 else ''}", n >= r["caution_from_alleles"]


def summarize(latest: dict[str, dict | None]) -> list[dict]:
    """latest: var -> {"value", "time"} or None. Returns only markers that were tested."""
    g = clinical_rules()["genetics"]
    out = []
    for var in GENE_VARS:
        r = latest.get(var)
        if not r:
            continue
        text, flag = _interpret(var, r["value"])
        out.append({"marker": var, "label": g[_RULE_KEY[var]]["label"], "value": r["value"],
                    "result": text, "flag": flag, "tested": r.get("time"), "simulated": True,
                    "source": g[_RULE_KEY[var]]["source"]})
    return out


def dkd_odds_ratio(prs_percentile: float | None) -> float:
    if prs_percentile is None:
        return 1.0
    r = clinical_rules()["genetics"]["ckd_prs"]
    if prs_percentile >= r["high_from_percentile"]:
        return float(r["odds_ratio_high"])
    if prs_percentile < r["low_below_percentile"]:
        return float(r["odds_ratio_low"])
    return 1.0


def apply_odds_ratio(p: float, odds_ratio: float) -> float:
    if odds_ratio == 1.0 or p <= 0 or p >= 1:
        return p
    o = p / (1 - p) * odds_ratio
    return o / (1 + o)


def drug_cautions(genetics: list[dict]) -> dict[str, list[str]]:
    g = clinical_rules()["genetics"]
    flagged = {m["marker"] for m in genetics if m["flag"]}
    out: dict[str, list[str]] = {"sulfonylurea": [], "metformin": []}
    if "tcf7l2_rs7903146" in flagged:
        out["sulfonylurea"].append(g["tcf7l2_rs7903146"]["caution"] + " (genetic, simulated)")
    if "cyp2c9_phenotype" in flagged:
        out["sulfonylurea"].append(g["cyp2c9_phenotype"]["caution"] + " (genetic, simulated)")
    if "slc22a1_reduced_alleles" in flagged:
        out["metformin"].append(g["slc22a1_reduced_alleles"]["caution"] + " (genetic, simulated)")
    return out
