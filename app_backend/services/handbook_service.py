"""
Statistical handbook service.

Provides a plain-language, data-independent glossary of core statistics
concepts (p-value, alpha, hypotheses, assumptions, etc.) plus one entry per
supported hypothesis test, for a reference/glossary page in the app.

Also builds the grounding context used by the handbook chatbot: the general
concept explanation for whichever test was actually chosen for the user's
uploaded dataset, plus the concrete numbers from that result (test statistic,
p-value, rationale, assumption checks), so the chatbot can explain *why this
specific test was picked and what its numbers mean* rather than only give
textbook definitions.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .stats_service import ACTIVE_TEST_DESCRIPTIONS, SUPPORTED_TESTS, TEST_DISPLAY_NAMES


def _fmt(x: Optional[float], nd: int = 5) -> str:
    return f"{x:.{nd}f}" if isinstance(x, (int, float)) and not isinstance(x, bool) else "—"


# ── Core, test-agnostic statistics concepts ────────────────────────

CONCEPT_HANDBOOK: Dict[str, Dict[str, str]] = {
    "hypothesis": {
        "title": "Null & Alternative Hypothesis",
        "what": (
            "The null hypothesis (H0) says 'no effect / no difference / no relationship'. "
            "The alternative hypothesis (H1) says the opposite — there IS an effect, "
            "difference, or relationship. A statistical test is a formal way of deciding "
            "whether your data gives strong enough evidence to reject H0."
        ),
        "why_it_matters": (
            "You never 'prove' H1 true. You either reject H0 (evidence favors a real "
            "effect) or fail to reject it (not enough evidence — which is not the same "
            "as proving there's no effect)."
        ),
        "example": (
            "H0: mean test score is the same for both teaching methods. "
            "H1: mean test score differs between the two methods."
        ),
    },
    "p_value": {
        "title": "P-Value",
        "what": (
            "The probability of seeing a result at least as extreme as yours, if the null "
            "hypothesis were actually true. It is not the probability that H0 is true, and "
            "it is not the probability your finding is a fluke."
        ),
        "why_it_matters": (
            "A small p-value means your data would be unlikely under 'no effect', so it's "
            "evidence against H0. Compare it to alpha to decide: p < alpha means "
            "statistically significant."
        ),
        "example": "p = 0.02 means: if there were truly no difference, data this extreme would show up about 2% of the time.",
    },
    "alpha": {
        "title": "Significance Level (Alpha)",
        "what": (
            "The threshold you pick before running the test for how much risk of a false "
            "positive (rejecting H0 when it's actually true) you're willing to accept. "
            "0.05 (5%) is the conventional default."
        ),
        "why_it_matters": (
            "Alpha is a judgment call, not a law of nature. A stricter alpha (e.g. 0.01) "
            "reduces false positives but makes it harder to detect a real effect."
        ),
        "example": "With alpha = 0.05, a p-value of 0.03 is significant; a p-value of 0.08 is not.",
    },
    "test_statistic": {
        "title": "Test Statistic",
        "what": (
            "A single number (e.g. t, F, chi-square, r) computed from your data that "
            "summarizes how far your observed result is from what H0 predicts, in "
            "standardized units."
        ),
        "why_it_matters": (
            "The p-value is derived from this number and the test's reference "
            "distribution — the test statistic is the raw signal, the p-value is its "
            "translation into 'how surprising is this'."
        ),
        "example": "A t-statistic of 3.2 means the observed group difference is 3.2 standard errors away from zero.",
    },
    "type_errors": {
        "title": "Type I & Type II Errors",
        "what": (
            "Type I error: rejecting H0 when it's actually true (a false positive). "
            "Type II error: failing to reject H0 when it's actually false (a false "
            "negative, often from too small a sample or a small true effect)."
        ),
        "why_it_matters": (
            "Alpha directly controls your Type I error rate. Statistical power (1 minus "
            "the Type II error rate) grows with sample size and effect size."
        ),
        "example": "Approving an ineffective drug (Type I) vs. rejecting an effective one (Type II).",
    },
    "assumptions": {
        "title": "Test Assumptions",
        "what": (
            "Every test relies on conditions about the data — common ones are normality "
            "(the variable is roughly bell-shaped), equal variance (groups spread out "
            "similarly), and independence (observations don't influence each other)."
        ),
        "why_it_matters": (
            "If a test's assumptions are badly violated, its p-value can be misleading. "
            "This app checks the relevant assumptions for you and reports them alongside "
            "each result."
        ),
        "example": "An independent t-test assumes each group is roughly normal and the two groups have similar variance.",
    },
    "confidence_interval": {
        "title": "Confidence Interval",
        "what": (
            "A range of plausible values for the true population effect, built from your "
            "sample. A 95% confidence interval means: if you repeated the study many "
            "times, about 95% of such intervals would contain the true value."
        ),
        "why_it_matters": (
            "A p-value only says 'significant or not' — a confidence interval also tells "
            "you the size and precision of the effect, which matters for practical "
            "importance."
        ),
        "example": "A 95% CI of [2.1, 8.4] for a mean difference suggests the true difference is likely in that range.",
    },
    "effect_size": {
        "title": "Effect Size",
        "what": (
            "A standardized measure of how large a difference or relationship is, "
            "independent of sample size (e.g. Cohen's d, R-squared, correlation "
            "coefficient r)."
        ),
        "why_it_matters": (
            "With a large enough sample, even a tiny, unimportant difference can be "
            "'statistically significant'. Effect size tells you whether it's practically "
            "meaningful."
        ),
        "example": "r = 0.9 is a strong correlation; r = 0.1 is a weak one, even if both are statistically significant.",
    },
}

# ── Per-test explanations, layered on top of ACTIVE_TEST_DESCRIPTIONS ──

_TEST_WHY: Dict[str, str] = {
    "independent_ttest": (
        "Use it when comparing the average of a numeric outcome between exactly two "
        "independent groups. It assumes each group is roughly normally distributed and "
        "the two groups have similar variance — the app checks both automatically."
    ),
    "pearson_correlation": (
        "Use it to quantify how strongly two numeric variables move together, on a scale "
        "from -1 (perfectly opposite) to +1 (perfectly together). It only captures "
        "*linear* relationships and assumes both variables are roughly normal."
    ),
    "simple_linear_regression": (
        "Use it when you want to predict or explain one numeric variable from another, "
        "not just measure association. It gives you a slope (effect per unit change) "
        "in addition to a p-value."
    ),
    "chi_square": (
        "Use it when both variables are categorical (groups/labels, not numbers). It "
        "compares the counts you actually observed in each category combination to the "
        "counts you'd expect if the two variables were unrelated."
    ),
    "one_way_anova": (
        "Use it when comparing the average of a numeric outcome across three or more "
        "independent groups — a t-test only handles two. A significant result means at "
        "least one group differs, not necessarily all of them."
    ),
}

_TEST_EXAMPLE: Dict[str, str] = {
    "independent_ttest": "Comparing average test scores between a treatment group and a control group.",
    "pearson_correlation": "Checking whether hours studied and exam score tend to rise together.",
    "simple_linear_regression": "Predicting monthly sales from advertising spend.",
    "chi_square": "Checking whether smoking status is associated with a disease diagnosis.",
    "one_way_anova": "Comparing average yield across three different fertilizer types.",
}


def _test_concept(test_name: str) -> Dict[str, str]:
    return {
        "title": TEST_DISPLAY_NAMES.get(test_name, test_name),
        "what": ACTIVE_TEST_DESCRIPTIONS.get(test_name, ""),
        "why_it_matters": _TEST_WHY.get(test_name, ""),
        "example": _TEST_EXAMPLE.get(test_name, ""),
    }


def list_concepts() -> List[Dict[str, Any]]:
    """Full glossary: core concepts first, then one entry per supported test."""
    concepts: List[Dict[str, Any]] = []
    for key, entry in CONCEPT_HANDBOOK.items():
        concepts.append({"key": key, "category": "concept", **entry})
    for test_name in SUPPORTED_TESTS:
        concepts.append({"key": test_name, "category": "test", **_test_concept(test_name)})
    return concepts


def describe_test_selection_context(
    test_name: Optional[str],
    variables_used: Dict[str, str],
    rationale: Optional[str],
    statistic: Optional[float],
    p_value: Optional[float],
    alpha: float,
    significant: Optional[bool],
    assumption_checks: List[Dict[str, Any]],
) -> str:
    """
    Build a compact text block grounding the handbook chatbot in whichever
    test was actually run for the user's hypothesis: the general explanation
    of that test plus the concrete numbers and rationale from their result.
    Returns an empty string if no test result was supplied (pure glossary Q&A).
    """
    if not test_name:
        return ""

    concept = _test_concept(test_name)
    parts = [
        f"Test performed: {concept['title']} ({test_name}).",
        f"What this test does: {concept['what']}",
        f"When it's the right choice: {concept['why_it_matters']}",
    ]
    if variables_used:
        cols = ", ".join(f"{role}='{col}'" for role, col in variables_used.items())
        parts.append(f"Columns used: {cols}.")
    if rationale:
        parts.append(f"Why the app picked this test for this question: {rationale}")
    parts.append(
        f"Result: statistic={_fmt(statistic, 4)}, p-value={_fmt(p_value)}, alpha={alpha}, "
        f"significant={'yes' if significant else 'no' if significant is not None else 'unknown'}."
    )
    for check in assumption_checks:
        name = check.get("name", "")
        passed = check.get("passed")
        detail = check.get("detail", "")
        status = "passed" if passed else "failed"
        parts.append(f"Assumption check — {name}: {status}. {detail}")

    return "\n".join(p for p in parts if p)
