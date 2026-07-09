"""
Statistics service.
1. Infers schema from an uploaded CSV/XLSX.
2. Calls the LLM to select the most appropriate statistical test.
3. Runs the test with SciPy / statsmodels.
4. Asks the LLM to produce a plain-language explanation.

ACTIVE TESTS (4):
  - independent_ttest      : Independent Samples T-Test
  - pearson_correlation    : Correlation (Pearson)
  - simple_linear_regression : Simple Linear Regression
  - chi_square             : Chi-Square Test of Independence

COMMENTED-OUT TESTS (still in code, not selectable):
  - paired_ttest, one_sample_ttest, spearman_correlation,
    multiple_linear_regression, logistic_regression, one_way_anova,
    mann_whitney_u, kruskal_wallis, wilcoxon_signed_rank
"""

from __future__ import annotations

import json
import logging
import re
import traceback
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from openai import OpenAI
from ..config import OPENAI_API_KEY, OPENAI_CHAT_MODEL, OPENAI_MAX_OUTPUT_TOKENS

logger = logging.getLogger(__name__)

_client: OpenAI | None = None


class StatisticalAnalysisError(ValueError):
    """Raised when the dataset or LLM selection is incompatible with the requested analysis."""


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        if not OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not set")
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client


# ──────────────────────────────────────────────────────────────────
# Schema helpers
# ──────────────────────────────────────────────────────────────────

def profile_dataframe(df: pd.DataFrame) -> Dict[str, Any]:
    """Return a JSON-serialisable profile of a DataFrame."""
    profile: Dict[str, Any] = {
        "rows": int(len(df)),
        "columns": [],
    }
    for col in df.columns:
        series = df[col].dropna()
        col_info: Dict[str, Any] = {
            "name": col,
            "dtype": str(df[col].dtype),
            "null_count": int(df[col].isna().sum()),
            "unique_count": int(series.nunique()),
        }
        if pd.api.types.is_numeric_dtype(df[col]):
            col_info["type"] = "numeric"
            col_info["min"] = float(series.min()) if len(series) else None
            col_info["max"] = float(series.max()) if len(series) else None
            col_info["mean"] = float(series.mean()) if len(series) else None
        else:
            col_info["type"] = "categorical"
            col_info["sample_values"] = series.value_counts().head(5).index.tolist()
        profile["columns"].append(col_info)

    # 5-row preview (string-safe)
    preview_df = df.head(5).fillna("").astype(str)
    profile["preview"] = preview_df.to_dict(orient="records")
    return profile


# ──────────────────────────────────────────────────────────────────
# Supported tests — ACTIVE vs COMMENTED
# ──────────────────────────────────────────────────────────────────

# ACTIVE: Only these 4 tests are available to users and the LLM.
SUPPORTED_TESTS = [
    "independent_ttest",
    "pearson_correlation",
    "simple_linear_regression",
    "chi_square",
    "one_way_anova",
    # --- COMMENTED OUT (not available) ---
    # "paired_ttest",
    # "one_sample_ttest",
    # "spearman_correlation",
    # "multiple_linear_regression",
    # "logistic_regression",
    # "mann_whitney_u",
    # "kruskal_wallis",
    # "wilcoxon_signed_rank",
]

# Human-readable display names for ALL tests (active + commented)
TEST_DISPLAY_NAMES = {
    "independent_ttest": "Independent Samples T-Test",
    "pearson_correlation": "Pearson Correlation",
    "simple_linear_regression": "Simple Linear Regression",
    "chi_square": "Chi-Square Test of Independence",
    "one_way_anova": "One-Way ANOVA",
    # --- COMMENTED OUT ---
    # "paired_ttest": "Paired Samples T-Test",
    # "one_sample_ttest": "One-Sample T-Test",
    # "spearman_correlation": "Spearman Correlation",
    # "multiple_linear_regression": "Multiple Linear Regression",
    # "logistic_regression": "Logistic Regression",
    # "mann_whitney_u": "Mann-Whitney U Test",
    # "kruskal_wallis": "Kruskal-Wallis Test",
    # "wilcoxon_signed_rank": "Wilcoxon Signed-Rank Test",
    "unsupported": "Analysis Not Supported",
}

# Active display names (for user-facing messages about what IS available)
ACTIVE_TEST_DISPLAY_NAMES = {k: TEST_DISPLAY_NAMES[k] for k in SUPPORTED_TESTS}

# Returned by the LLM when no implemented test fits the question / data
UNSUPPORTED_TEST = "unsupported"
LLM_SELECTABLE_TESTS = SUPPORTED_TESTS + [UNSUPPORTED_TEST]

# Clear user-facing description of each active test's purpose
ACTIVE_TEST_DESCRIPTIONS = {
    "independent_ttest": (
        "Independent T-Test — compares the mean of a numeric variable between exactly "
        "2 distinct groups (e.g. male vs. female scores)."
    ),
    "pearson_correlation": (
        "Pearson Correlation — measures the linear relationship between two numeric variables "
        "(e.g. height vs. weight)."
    ),
    "simple_linear_regression": (
        "Simple Linear Regression — predicts a numeric outcome from one numeric predictor "
        "(e.g. predicting sales from advertising spend)."
    ),
    "chi_square": (
        "Chi-Square Test — checks whether two categorical variables are associated "
        "(e.g. smoking status vs. disease diagnosis)."
    ),
    "one_way_anova": (
        "One-Way ANOVA — compares the mean of a numeric variable across 3 or more "
        "distinct groups (e.g. exam scores across 3 teaching methods)."
    ),
}


def _unsupported_analysis_result(
    question: str,
    message: str,
    rationale: str = "",
    alpha: float = 0.05,
) -> Dict[str, Any]:
    """Build a StatTestResult-compatible payload without running any test."""
    available_list = "\n".join(
        f"  • {desc}" for desc in ACTIVE_TEST_DESCRIPTIONS.values()
    )
    if not message:
        message = (
            "Sorry, this question cannot be answered with the statistical tests currently "
            "available in this application.\n\n"
            f"Currently available tests:\n{available_list}"
        )
    return {
        "test_name": UNSUPPORTED_TEST,
        "test_display_name": TEST_DISPLAY_NAMES[UNSUPPORTED_TEST],
        "variables_used": {},
        "rationale": rationale or message,
        "statistic": None,
        "p_value": None,
        "additional_stats": {},
        "assumption_checks": [],
        "interpretation": "",
        "plain_explanation": message,
        "significant": None,
        "alpha": alpha,
        "error": message,
    }


# ──────────────────────────────────────────────────────────────────
# Variable normalization helpers
# ──────────────────────────────────────────────────────────────────

def _clean_variables(variables: Dict[str, Any]) -> Dict[str, Any]:
    """Drop null/empty LLM variable entries."""
    cleaned: Dict[str, Any] = {}
    for key, value in variables.items():
        if value is None:
            continue
        if isinstance(value, str) and value.strip().lower() in {"", "null", "none"}:
            continue
        if isinstance(value, (list, tuple)) and len(value) == 0:
            continue
        cleaned[key] = value
    return cleaned


def _collect_role_columns(variables: Dict[str, Any]) -> List[str]:
    """Gather distinct column names from x / y / group roles (LLM output varies)."""
    cols: List[str] = []
    for key in ("x", "y", "group"):
        raw = variables.get(key)
        if raw is None:
            continue
        name = str(raw).strip()
        if name.lower() in {"", "null", "none"}:
            continue
        if name not in cols:
            cols.append(name)
    return cols


def _normalize_xy_pair(
    variables: Dict[str, Any],
    df: pd.DataFrame,
    *,
    require_numeric: bool = False,
) -> Dict[str, str]:
    """Map x / y / group roles to a pair of columns (for correlation, paired tests)."""
    cols = _collect_role_columns(variables)
    if len(cols) < 2:
        raise StatisticalAnalysisError(
            "This test requires two columns. Set x and y (or y and group) to column names."
        )
    col_a, col_b = cols[0], cols[1]
    for col in (col_a, col_b):
        if col not in df.columns:
            raise StatisticalAnalysisError(
                f"Column '{col}' not found. Available: {list(df.columns)}"
            )
        if require_numeric and not pd.api.types.is_numeric_dtype(df[col]):
            raise StatisticalAnalysisError(
                f"Column '{col}' must be numeric for this test."
            )
    return {"x": col_a, "y": col_b}


def _normalize_group_and_value(
    variables: Dict[str, Any],
    df: pd.DataFrame,
) -> Dict[str, str]:
    """Map roles to group column (x/group) and numeric value column (y)."""
    cols = _collect_role_columns(variables)
    if len(cols) < 2:
        raise StatisticalAnalysisError(
            "This test requires a grouping column and a numeric outcome column."
        )
    col_a, col_b = cols[0], cols[1]
    a_numeric = pd.api.types.is_numeric_dtype(df[col_a])
    b_numeric = pd.api.types.is_numeric_dtype(df[col_b])

    if a_numeric and not b_numeric:
        group_col, value_col = col_b, col_a
    elif b_numeric and not a_numeric:
        group_col, value_col = col_a, col_b
    else:
        y_col = variables.get("y")
        if y_col and y_col in df.columns and pd.api.types.is_numeric_dtype(df[y_col]):
            value_col = y_col
            group_col = next((c for c in cols if c != y_col), col_a)
        elif pd.api.types.is_numeric_dtype(df[col_b]):
            group_col, value_col = col_a, col_b
        else:
            group_col, value_col = col_a, col_b

    if not pd.api.types.is_numeric_dtype(df[value_col]):
        raise StatisticalAnalysisError(
            f"Column '{value_col}' must be numeric; '{group_col}' is the grouping variable."
        )
    return {"x": group_col, "y": value_col, "group": group_col}


def _normalize_chi_square_variables(
    variables: Dict[str, Any],
    df: pd.DataFrame,
) -> Dict[str, str]:
    """Map x / y / group roles to exactly two columns for chi-square."""
    cols = _collect_role_columns(variables)
    if len(cols) < 2:
        raise StatisticalAnalysisError(
            "Chi-square requires two categorical columns. "
            "Set x and y (e.g. x='smoking', y='disease') or y and group."
        )
    for col in cols[:2]:
        if col not in df.columns:
            raise StatisticalAnalysisError(
                f"Column '{col}' not found. Available: {list(df.columns)}"
            )
    return {"x": cols[0], "y": cols[1]}


# --- COMMENTED OUT: helpers for commented-out tests ---
# def _resolve_predictor_columns(...): ...  # used by multiple/logistic regression
# def _coerce_series_numeric(...): ...      # used by logistic regression
# def _encode_single_predictor(...): ...    # used by logistic/multiple regression
# def _encode_predictors(...): ...          # used by logistic/multiple regression
# def _encode_binary_outcome(...): ...      # used by logistic regression
# def _infer_popmean_from_question(...): .. # used by one_sample_ttest


def _format_variables_used(variables: Dict[str, Any]) -> Dict[str, str]:
    """Flatten variables for API response (Dict[str, str])."""
    out: Dict[str, str] = {}
    for key, value in variables.items():
        if value is None:
            continue
        if key == "predictors" and isinstance(value, list):
            out["predictors"] = ", ".join(str(v) for v in value)
        elif isinstance(value, str):
            out[key] = value
    return out


# ──────────────────────────────────────────────────────────────────
# Test normalization
# ──────────────────────────────────────────────────────────────────

def normalize_test_selection(
    df: pd.DataFrame,
    test_name: str,
    variables: Dict[str, Any],
    question: str = "",
) -> Tuple[str, Dict[str, Any]]:
    """
    Validate and align LLM test choice with actual column types.
    Only active tests are processed; any other test raises an error.
    """
    variables = _clean_variables(variables)

    if test_name not in SUPPORTED_TESTS:
        raise StatisticalAnalysisError(
            f"Test '{test_name}' is not currently available. "
            f"Available: {', '.join(SUPPORTED_TESTS)}"
        )

    if test_name == "chi_square":
        return test_name, _normalize_chi_square_variables(variables, df)

    if test_name == "pearson_correlation":
        return test_name, _normalize_xy_pair(variables, df, require_numeric=True)

    if test_name == "simple_linear_regression":
        pair = _normalize_xy_pair(variables, df, require_numeric=True)
        x_col, y_col = pair["x"], pair["y"]
        if not pd.api.types.is_numeric_dtype(df[x_col]):
            raise StatisticalAnalysisError(
                f"Column '{x_col}' must be numeric for simple linear regression."
            )
        if not pd.api.types.is_numeric_dtype(df[y_col]):
            raise StatisticalAnalysisError(
                f"Outcome column '{y_col}' must be numeric for simple linear regression."
            )
        return test_name, pair

    if test_name == "independent_ttest":
        mapped = _normalize_group_and_value(variables, df)
        group_col = mapped["group"]
        # Independent t-test: exactly 2 groups required
        unique_groups = df[group_col].dropna().unique()
        if len(unique_groups) < 2:
            raise StatisticalAnalysisError(
                f"Independent t-test requires at least 2 distinct groups in '{group_col}'; "
                f"found {len(unique_groups)}."
            )
        if len(unique_groups) > 2:
            raise StatisticalAnalysisError(
                f"Independent t-test compares exactly 2 groups; '{group_col}' has "
                f"{len(unique_groups)} unique values. Consider a different approach."
            )
        return test_name, mapped

    if test_name == "one_way_anova":
        mapped = _normalize_group_and_value(variables, df)
        group_col = mapped["group"]
        unique_groups = df[group_col].dropna().unique()
        if len(unique_groups) < 3:
            raise StatisticalAnalysisError(
                f"One-way ANOVA requires at least 3 distinct groups in '{group_col}'; "
                f"found {len(unique_groups)}. For 2 groups use an independent t-test instead."
            )
        return test_name, mapped

    # --- COMMENTED OUT: normalization branches for inactive tests ---
    # if test_name == "one_sample_ttest": ...
    # if test_name in ("paired_ttest", "wilcoxon_signed_rank"): ...
    # if test_name == "spearman_correlation": ...
    # if test_name in ("mann_whitney_u", "kruskal_wallis"): ...
    # if test_name in ("multiple_linear_regression",): ...
    # if test_name == "logistic_regression": ...

    raise StatisticalAnalysisError(f"Unhandled test: {test_name}")


# ──────────────────────────────────────────────────────────────────
# LLM test selector
# ──────────────────────────────────────────────────────────────────

def select_test_via_llm(question: str, schema_profile: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ask the LLM to pick the best statistical test given the question and data schema.
    The LLM is made aware of ONLY the 4 active tests.
    Returns a dict with keys: test, variables, rationale.
    """
    sample_rows = schema_profile.get("preview", [])

    available_tests_block = "\n".join(
        f'  "{k}": {v}' for k, v in ACTIVE_TEST_DESCRIPTIONS.items()
    )

    # ── Enrich the schema with per-column unique-group counts so the LLM
    #    can reason about "exactly 2 groups" without guessing. ────────────
    col_type_summary = []
    for col in schema_profile.get("columns", []):
        ctype  = col.get("type", "?")
        nuniq  = col.get("unique_count", "?")
        sample = ""
        if ctype == "categorical":
            sv = col.get("sample_values", [])
            sample = f", values={sv}"
        col_type_summary.append(
            f"  - {col['name']}: {ctype}, {nuniq} unique values{sample}"
        )
    col_type_block = "\n".join(col_type_summary)

    system_prompt = (
        "You are an expert statistician and gatekeeper for a statistical analysis application.\n"
        "Your ONLY job: decide whether the user's question can be answered by exactly one of the\n"
        "5 SUPPORTED TESTS below, or whether it must be declared unsupported.\n\n"

        # ── 1. SUPPORTED TESTS ────────────────────────────────────────────
        "══════════════════════════════════════════════════════════════\n"
        "SUPPORTED TESTS — the ONLY 5 tests this application can run:\n"
        "══════════════════════════════════════════════════════════════\n"
        f"{available_tests_block}\n\n"

        "Each test has STRICT structural requirements listed below.\n"
        "If the question cannot be mapped cleanly to one of these 5 tests, declare it unsupported.\n\n"

        # ── 2. EXACT REQUIREMENTS PER TEST ───────────────────────────────
        "══════════════════════════════════\n"
        "EXACT REQUIREMENTS PER TEST\n"
        "══════════════════════════════════\n\n"

        "1. independent_ttest\n"
        "   REQUIRES:\n"
        "   • Exactly ONE numeric outcome column (e.g. price, score, weight)\n"
        "   • Exactly ONE grouping column that has EXACTLY 2 distinct categories\n"
        "     (e.g. yes/no, male/female, treated/control)\n"

        "2. pearson_correlation\n"
        "   REQUIRES:\n"
        "   • Exactly TWO numeric columns\n"

        "3. simple_linear_regression\n"
        "   REQUIRES:\n"
        "   • Exactly ONE numeric predictor (independent variable, X)\n"
        "   • Exactly ONE numeric outcome (dependent variable, Y)\n"

        "4. chi_square\n"
        "   REQUIRES:\n"
        "   • Exactly TWO categorical (non-numeric) columns\n"
        "   Does NOT apply to one categorical + one numeric column — see one_way_anova below.\n\n"

        "5. one_way_anova\n"
        "   REQUIRES:\n"
        "   • Exactly ONE numeric outcome column (e.g. score, weight, price)\n"
        "   • Exactly ONE categorical grouping column with 3 OR MORE distinct categories\n"
        "     (e.g. teaching method, region, treatment group)\n"
        "   IMPORTANT: questions phrased as an 'association', 'relationship', or 'link' between\n"
        "   ONE categorical column (3+ groups) and ONE numeric column are ALSO answered by\n"
        "   one_way_anova — do not reject these as unsupported and do not confuse them with\n"
        "   chi_square, which only applies when BOTH columns are categorical.\n"
        "   USE THIS when the question asks about differences across 3+ groups.\n"
        "   Variables: set 'y' = numeric outcome, 'group' = categorical grouping column.\n\n"

        "══════════════════════════════════════════\n"
        "DECISION PROCESS — follow these steps:\n"
        "══════════════════════════════════════════\n"
        "Step 1. Count distinct columns/variables mentioned in the question.\n"
        "Step 2. Identify the role of each column.\n"
        "Step 3. Check each candidate test's EXACT REQUIREMENTS.\n"
        "Step 4. If exactly one test matches → choose it.\n"
        "        If no test matches → declare unsupported.\n"
        "Step 5. Verify the columns mentioned actually exist in the dataset schema.\n\n"

        "══════════════════════════════════════════\n"
        "RESPONSE FORMAT — valid JSON only, no markdown:\n"
        "══════════════════════════════════════════\n\n"

        "Option A — supported test:\n"
        "{\n"
        '  "test": "<one of: independent_ttest | pearson_correlation | simple_linear_regression | chi_square | one_way_anova>",\n'
        '  "variables": {\n'
        '    "x": "<single predictor or grouping column name, or null>",\n'
        '    "y": "<single outcome column name>",\n'
        '    "group": "<grouping column name or null>"\n'
        "  },\n"
        '  "rationale": "<which step matched, which test, and why no disqualifier fired>"\n'
        "}\n\n"

        f'Option B — not supported (test field MUST be exactly "{UNSUPPORTED_TEST}"):\n'
        "{\n"
        f'  "test": "{UNSUPPORTED_TEST}",\n'
        '  "message": "<polite explanation: (1) what the user asked for, (2) which specific rule\n'
        "    or disqualifier was triggered, (3) what the 5 available tests CAN do with this data.\n"
        '    Be specific — e.g. mention multiple regression, etc. by name.>",\n'
        '  "rationale": "<internal: which disqualifier fired and why>"\n'
        "}\n\n"

        "FINAL REMINDER: When in doubt, declare unsupported. Never force-fit a question to a\n"
        "test that does not match. A wrong test is worse than an honest 'not supported' message.\n"
        f"The column types in this dataset are:\n{col_type_block}\n"
    )

    user_msg = (
        f"Dataset schema:\n{json.dumps(schema_profile, indent=2, default=str)}\n\n"
        f"Sample rows (first 5 — use these to see real values and formats):\n"
        f"{json.dumps(sample_rows, indent=2, default=str)}\n\n"
        f"User question: {question}"
    )

    client = _get_client()
    resp = client.chat.completions.create(
        model=OPENAI_CHAT_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        temperature=0,
        max_tokens=600,
    )

    raw = (resp.choices[0].message.content or "").strip()
    raw = raw.replace("```json", "").replace("```", "").strip()

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        logger.error(f"LLM returned non-JSON for test selection: {raw}")
        raise ValueError(f"LLM returned invalid JSON: {raw}")

    test_id = result.get("test")
    if test_id not in LLM_SELECTABLE_TESTS:
        # If LLM chose a commented-out test, treat as unsupported
        logger.warning(
            f"LLM selected unavailable test '{test_id}'; treating as unsupported."
        )
        available_list = "\n".join(
            f"  • {desc}" for desc in ACTIVE_TEST_DESCRIPTIONS.values()
        )
        result = {
            "test": UNSUPPORTED_TEST,
            "message": (
                f"The analysis you requested ('{test_id}') is not currently available.\n\n"
                f"Currently available tests:\n{available_list}"
            ),
            "rationale": f"LLM selected '{test_id}' which is not in the active test list.",
        }

    if result.get("test") == UNSUPPORTED_TEST:
        if not result.get("message"):
            available_list = "\n".join(
                f"  • {desc}" for desc in ACTIVE_TEST_DESCRIPTIONS.values()
            )
            result["message"] = (
                result.get("rationale")
                or "This analysis is not available with the statistical tests implemented in this app.\n\n"
                f"Currently available tests:\n{available_list}"
            )
        logger.info("LLM marked question as unsupported: %s", result.get("message", "")[:120])
        return result

    return result


# ──────────────────────────────────────────────────────────────────
# Assumption checks
# ──────────────────────────────────────────────────────────────────

def check_normality(series: pd.Series) -> Tuple[bool, str]:
    from scipy import stats
    clean = series.dropna()
    if len(clean) < 3:
        return False, "Too few samples for normality check (need ≥ 3)"
    if len(clean) > 5000:
        # Shapiro-Wilk unreliable on large N; use D'Agostino-Pearson
        stat, p = stats.normaltest(clean)
        passed = bool(p > 0.05)
        return passed, f"D'Agostino-Pearson normality test: p={p:.4f} ({'normal' if passed else 'non-normal'})"
    stat, p = stats.shapiro(clean)
    passed = bool(p > 0.05)
    return passed, f"Shapiro-Wilk: W={stat:.4f}, p={p:.4f} ({'normal' if passed else 'non-normal'})"


def check_equal_variance(groups: List[pd.Series]) -> Tuple[bool, str]:
    from scipy import stats
    clean = [g.dropna() for g in groups if len(g.dropna()) >= 2]
    if len(clean) < 2:
        return True, "Could not check variance (insufficient groups)"
    stat, p = stats.levene(*clean)
    passed = bool(p > 0.05)
    return passed, f"Levene's test: stat={stat:.4f}, p={p:.4f} ({'equal variance' if passed else 'unequal variance'})"


# ──────────────────────────────────────────────────────────────────
# ACTIVE Statistical test runners
# ──────────────────────────────────────────────────────────────────

def _run_independent_ttest(df: pd.DataFrame, variables: Dict[str, str]) -> Dict[str, Any]:
    """
    Independent Samples T-Test.
    Requires: one grouping column (exactly 2 groups) + one numeric outcome column.
    Robustness: uses Welch's t-test (equal_var=False) when Levene's test fails,
    so unequal variances are handled gracefully.
    """
    from scipy import stats

    mapped = _normalize_group_and_value(variables, df)
    group_col, value_col = mapped["group"], mapped["y"]

    groups = df[group_col].dropna().unique()
    if len(groups) < 2:
        raise StatisticalAnalysisError(
            f"Column '{group_col}' has fewer than 2 groups. "
            "Independent t-test requires exactly 2 groups."
        )

    g1_label, g2_label = groups[0], groups[1]
    g1 = pd.to_numeric(df[df[group_col] == g1_label][value_col], errors="coerce").dropna()
    g2 = pd.to_numeric(df[df[group_col] == g2_label][value_col], errors="coerce").dropna()

    if len(g1) < 2:
        raise StatisticalAnalysisError(
            f"Group '{g1_label}' has fewer than 2 observations after removing missing values."
        )
    if len(g2) < 2:
        raise StatisticalAnalysisError(
            f"Group '{g2_label}' has fewer than 2 observations after removing missing values."
        )

    norm1_ok, norm1_detail = check_normality(g1)
    norm2_ok, norm2_detail = check_normality(g2)
    var_ok, var_detail = check_equal_variance([g1, g2])

    # Welch's t-test when variances are unequal (more robust default)
    stat, p = stats.ttest_ind(g1, g2, equal_var=var_ok)

    # Cohen's d effect size (pooled SD)
    pooled_std = np.sqrt(
        ((len(g1) - 1) * g1.std() ** 2 + (len(g2) - 1) * g2.std() ** 2)
        / (len(g1) + len(g2) - 2)
    )
    cohens_d = float((g1.mean() - g2.mean()) / pooled_std) if pooled_std > 0 else 0.0

    return {
        "statistic": float(stat),
        "p_value": float(p),
        "additional_stats": {
            "group1": str(g1_label),
            "group1_mean": round(float(g1.mean()), 4),
            "group1_std": round(float(g1.std()), 4),
            "group1_n": int(len(g1)),
            "group2": str(g2_label),
            "group2_mean": round(float(g2.mean()), 4),
            "group2_std": round(float(g2.std()), 4),
            "group2_n": int(len(g2)),
            "cohens_d": round(cohens_d, 4),
            "equal_variance_assumed": bool(var_ok),
            "test_variant": "Student's t-test" if var_ok else "Welch's t-test (unequal variance)",
        },
        "assumption_checks": [
            {"name": f"Normality ({g1_label})", "passed": norm1_ok, "detail": norm1_detail},
            {"name": f"Normality ({g2_label})", "passed": norm2_ok, "detail": norm2_detail},
            {"name": "Equal Variance (Levene)", "passed": var_ok, "detail": var_detail},
        ],
    }


def _run_pearson_correlation(df: pd.DataFrame, variables: Dict[str, str]) -> Dict[str, Any]:
    """
    Pearson Correlation.
    Requires: two numeric columns.
    Robustness: drops rows with any NaN in either column, needs ≥ 3 complete pairs.
    """
    from scipy import stats

    pair = _normalize_xy_pair(variables, df, require_numeric=True)
    x_col, y_col = pair["x"], pair["y"]
    clean = df[[x_col, y_col]].apply(pd.to_numeric, errors="coerce").dropna()

    if len(clean) < 3:
        raise StatisticalAnalysisError(
            f"Pearson correlation needs at least 3 complete (non-missing) row pairs; "
            f"got {len(clean)}."
        )

    if clean[x_col].std() == 0:
        raise StatisticalAnalysisError(
            f"Column '{x_col}' has zero variance (all values are identical). "
            "Pearson correlation requires variability in both columns."
        )
    if clean[y_col].std() == 0:
        raise StatisticalAnalysisError(
            f"Column '{y_col}' has zero variance (all values are identical). "
            "Pearson correlation requires variability in both columns."
        )

    r, p = stats.pearsonr(clean[x_col], clean[y_col])

    strength = (
        "very strong" if abs(r) >= 0.8 else
        "strong" if abs(r) >= 0.6 else
        "moderate" if abs(r) >= 0.4 else
        "weak" if abs(r) >= 0.2 else "negligible"
    )
    direction = "positive" if r > 0 else "negative"

    norm_x_ok, norm_x_detail = check_normality(clean[x_col])
    norm_y_ok, norm_y_detail = check_normality(clean[y_col])

    return {
        "statistic": round(float(r), 6),
        "p_value": float(p),
        "additional_stats": {
            "r_squared": round(float(r ** 2), 6),
            "n": int(len(clean)),
            "strength": strength,
            "direction": direction,
        },
        "assumption_checks": [
            {"name": f"Normality ({x_col})", "passed": norm_x_ok, "detail": norm_x_detail},
            {"name": f"Normality ({y_col})", "passed": norm_y_ok, "detail": norm_y_detail},
        ],
    }


def _run_simple_linear_regression(df: pd.DataFrame, variables: Dict[str, str]) -> Dict[str, Any]:
    """
    Simple Linear Regression.
    Requires: one numeric predictor (x) and one numeric outcome (y).
    Robustness: drops rows with NaN in either column; needs ≥ 3 complete rows.
    Checks for zero variance in predictor (would produce NaN coefficients).
    """
    from scipy import stats

    x_col = variables.get("x")
    y_col = variables.get("y")
    if not x_col or not y_col:
        raise StatisticalAnalysisError(
            "simple_linear_regression requires 'x' (predictor) and 'y' (outcome) columns."
        )
    for col in (x_col, y_col):
        if col not in df.columns:
            raise StatisticalAnalysisError(
                f"Column '{col}' not found. Available: {list(df.columns)}"
            )

    clean = df[[x_col, y_col]].copy()
    clean[x_col] = pd.to_numeric(clean[x_col], errors="coerce")
    clean[y_col] = pd.to_numeric(clean[y_col], errors="coerce")
    clean = clean.dropna()

    if len(clean) < 3:
        raise StatisticalAnalysisError(
            f"Simple linear regression needs at least 3 complete rows; got {len(clean)}."
        )
    if clean[x_col].std() == 0:
        raise StatisticalAnalysisError(
            f"Predictor column '{x_col}' has zero variance. Regression cannot be computed."
        )

    slope, intercept, r, p, se = stats.linregress(clean[x_col], clean[y_col])

    return {
        "statistic": round(float(slope / se), 4),   # t-statistic
        "p_value": float(p),
        "additional_stats": {
            "slope": round(float(slope), 6),
            "intercept": round(float(intercept), 6),
            "r_squared": round(float(r ** 2), 6),
            "std_error": round(float(se), 6),
            "n": int(len(clean)),
            "equation": f"{y_col} = {slope:.4f} × {x_col} + ({intercept:.4f})",
        },
        "assumption_checks": [],
    }


def _run_chi_square(df: pd.DataFrame, variables: Dict[str, str]) -> Dict[str, Any]:
    """
    Chi-Square Test of Independence.
    Requires: two categorical (non-numeric) columns.
    Robustness: checks expected cell counts ≥ 5 (assumption flagged, not blocking).
    Warns when min expected cell count < 5; still runs but adds a warning.
    """
    from scipy import stats

    pair = _normalize_chi_square_variables(variables, df)
    x_col, y_col = pair["x"], pair["y"]

    # Drop rows where either column is NaN
    clean = df[[x_col, y_col]].dropna()
    if len(clean) < 2:
        raise StatisticalAnalysisError(
            f"Chi-square test needs at least 2 complete rows; got {len(clean)}."
        )

    contingency = pd.crosstab(clean[x_col], clean[y_col])

    if contingency.shape[0] < 2 or contingency.shape[1] < 2:
        raise StatisticalAnalysisError(
            "Chi-square requires both variables to have at least 2 distinct categories. "
            f"'{x_col}' has {contingency.shape[0]}, '{y_col}' has {contingency.shape[1]}."
        )

    chi2, p, dof, expected = stats.chi2_contingency(contingency)

    # Cramér's V effect size
    n = int(contingency.values.sum())
    min_dim = min(contingency.shape) - 1
    cramers_v = float(np.sqrt(chi2 / (n * min_dim))) if min_dim > 0 and n > 0 else 0.0

    min_expected = float(expected.min())
    cells_below_5 = int((expected < 5).sum())
    total_cells = int(expected.size)

    assumption_detail = (
        f"Min expected count: {min_expected:.2f}"
        + (
            f" — WARNING: {cells_below_5}/{total_cells} cells have expected count < 5. "
            "Results may be unreliable; consider merging categories."
            if min_expected < 5 else ""
        )
    )

    return {
        "statistic": round(float(chi2), 4),
        "p_value": float(p),
        "additional_stats": {
            "degrees_of_freedom": int(dof),
            "n": n,
            "cramers_v": round(cramers_v, 4),
            "contingency_table": contingency.to_dict(),
        },
        "assumption_checks": [
            {
                "name": "Expected cell counts ≥ 5",
                "passed": bool(min_expected >= 5),
                "detail": assumption_detail,
            }
        ],
    }


def _run_one_way_anova(df: pd.DataFrame, variables: Dict[str, str]) -> Dict[str, Any]:
    """
    One-Way ANOVA.
    Requires: one numeric outcome (y) and one categorical grouping column (group).
    Needs at least 3 groups, each with ≥ 2 observations.
    Assumption checks: normality per group (Shapiro-Wilk), homogeneity of variance (Levene).
    Additional stats: eta-squared effect size, per-group descriptives.
    """
    from scipy import stats

    y_col = variables.get("y")
    group_col = variables.get("group")
    if not y_col or not group_col:
        raise StatisticalAnalysisError(
            "one_way_anova requires 'y' (numeric outcome) and 'group' (categorical) columns."
        )
    for col in (y_col, group_col):
        if col not in df.columns:
            raise StatisticalAnalysisError(
                f"Column '{col}' not found. Available: {list(df.columns)}"
            )

    clean = df[[y_col, group_col]].copy()
    clean[y_col] = pd.to_numeric(clean[y_col], errors="coerce")
    clean = clean.dropna()

    if len(clean) < 6:
        raise StatisticalAnalysisError(
            f"One-way ANOVA needs at least 6 complete rows; got {len(clean)}."
        )

    groups = {name: grp[y_col].values for name, grp in clean.groupby(group_col)}
    if len(groups) < 3:
        raise StatisticalAnalysisError(
            f"One-way ANOVA requires at least 3 groups; found {len(groups)}: {list(groups.keys())}. "
            "For 2 groups consider an independent t-test instead."
        )
    small = [name for name, vals in groups.items() if len(vals) < 2]
    if small:
        raise StatisticalAnalysisError(
            f"Groups {small} have fewer than 2 observations. Each group needs at least 2."
        )

    f_stat, p_value = stats.f_oneway(*groups.values())

    # Eta-squared effect size
    all_values = clean[y_col].values
    grand_mean = all_values.mean()
    ss_between = sum(len(v) * (v.mean() - grand_mean) ** 2 for v in groups.values())
    ss_total = sum((val - grand_mean) ** 2 for val in all_values)
    eta_squared = round(float(ss_between / ss_total), 4) if ss_total > 0 else 0.0

    # Per-group descriptives
    group_stats = {
        name: {
            "n": int(len(vals)),
            "mean": round(float(vals.mean()), 4),
            "std": round(float(vals.std(ddof=1)), 4),
        }
        for name, vals in groups.items()
    }

    # Assumption checks
    assumption_checks = []

    # Normality per group (Shapiro-Wilk, only meaningful for n < 5000)
    for name, vals in groups.items():
        if len(vals) >= 3:
            _, norm_p = stats.shapiro(vals)
            passed = bool(norm_p > 0.05)
            assumption_checks.append({
                "name": f"Normality — {name}",
                "passed": passed,
                "detail": f"Shapiro-Wilk p = {norm_p:.4f} ({'normal' if passed else 'non-normal'})",
            })

    # Homogeneity of variance (Levene's test)
    lev_stat, lev_p = stats.levene(*groups.values())
    lev_passed = bool(lev_p > 0.05)
    assumption_checks.append({
        "name": "Homogeneity of variance (Levene's test)",
        "passed": lev_passed,
        "detail": (
            f"Levene's W = {lev_stat:.4f}, p = {lev_p:.4f} "
            f"({'equal variances' if lev_passed else 'unequal variances — consider Welch ANOVA'})"
        ),
    })

    return {
        "statistic": round(float(f_stat), 4),
        "p_value": float(p_value),
        "additional_stats": {
            "eta_squared": eta_squared,
            "n": int(len(clean)),
            "n_groups": len(groups),
            "group_stats": group_stats,
        },
        "assumption_checks": assumption_checks,
    }


# --- COMMENTED OUT: inactive test runners ---

# def _run_paired_ttest(df, variables): ...
# def _run_one_sample_ttest(df, variables): ...
# def _run_spearman_correlation(df, variables): ...
# def _run_multiple_linear_regression(df, variables): ...
# def _run_logistic_regression(df, variables): ...
# def _run_mann_whitney(df, variables): ...
# def _run_kruskal_wallis(df, variables): ...
# def _run_wilcoxon(df, variables): ...


# ──────────────────────────────────────────────────────────────────
# Test runner dispatcher — ACTIVE tests only
# ──────────────────────────────────────────────────────────────────

TEST_RUNNERS = {
    "independent_ttest": _run_independent_ttest,
    "pearson_correlation": _run_pearson_correlation,
    "simple_linear_regression": _run_simple_linear_regression,
    "chi_square": _run_chi_square,
    "one_way_anova": _run_one_way_anova,
    # --- COMMENTED OUT ---
    # "paired_ttest": _run_paired_ttest,
    # "one_sample_ttest": _run_one_sample_ttest,
    # "spearman_correlation": _run_spearman_correlation,
    # "multiple_linear_regression": _run_multiple_linear_regression,
    # "logistic_regression": _run_logistic_regression,
    # "mann_whitney_u": _run_mann_whitney,
    # "kruskal_wallis": _run_kruskal_wallis,
    # "wilcoxon_signed_rank": _run_wilcoxon,
}


# ──────────────────────────────────────────────────────────────────
# LLM plain-language explanation
# ──────────────────────────────────────────────────────────────────

def explain_results_via_llm(
    question: str,
    test_name: str,
    variables: Dict[str, str],
    results: Dict[str, Any],
    alpha: float = 0.05,
) -> Tuple[str, str]:
    """Return (interpretation, plain_explanation) from LLM."""

    p_value = results.get("p_value")
    significant = p_value is not None and p_value < alpha

    prompt = (
        f"A user asked: '{question}'\n\n"
        f"Statistical test performed: {TEST_DISPLAY_NAMES.get(test_name, test_name)}\n"
        f"Variables used: {json.dumps(variables)}\n"
        f"Results: {json.dumps(results.get('additional_stats', {}), default=str)}\n"
        f"Test statistic: {results.get('statistic')}\n"
        f"P-value: {p_value}\n"
        f"Significance level (alpha): {alpha}\n"
        f"Result is {'statistically significant' if significant else 'NOT statistically significant'}.\n\n"
        "Please provide:\n"
        "1. A short technical interpretation (1-2 sentences, for statisticians)\n"
        "2. A plain-language explanation (2-3 sentences) for someone with no statistics background\n\n"
        "Return ONLY valid JSON — no markdown:\n"
        '{"interpretation": "...", "plain_explanation": "..."}'
    )

    client = _get_client()
    resp = client.chat.completions.create(
        model=OPENAI_CHAT_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a statistician who communicates results clearly to both "
                    "technical and non-technical audiences."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        max_tokens=OPENAI_MAX_OUTPUT_TOKENS,
    )

    raw = (resp.choices[0].message.content or "").strip()
    raw = raw.replace("```json", "").replace("```", "").strip()

    try:
        parsed = json.loads(raw)
        return parsed.get("interpretation", ""), parsed.get("plain_explanation", "")
    except Exception:
        return raw, raw


# ──────────────────────────────────────────────────────────────────
# Main entry point
# ──────────────────────────────────────────────────────────────────

def run_statistical_analysis(
    df: pd.DataFrame,
    question: str,
    alpha: float = 0.05,
) -> Dict[str, Any]:
    """
    Full pipeline: profile → LLM selects test → run test → LLM explains.
    If the question cannot be answered with active tests, returns a polite
    unsupported result without raising an error.
    Returns a dict compatible with StatTestResult.
    """
    schema_profile = profile_dataframe(df)

    # Step 1: LLM selects test
    logger.info("Calling LLM for test selection...")
    try:
        selection = select_test_via_llm(question, schema_profile)
    except Exception as exc:
        logger.error(f"LLM test selection failed: {exc}")
        return _unsupported_analysis_result(
            question,
            message=(
                "An error occurred while analysing your question. "
                "Please rephrase or try a different question."
            ),
            rationale=str(exc),
            alpha=alpha,
        )

    test_name = selection.get("test", UNSUPPORTED_TEST)
    variables = selection.get("variables") or {}
    rationale = selection.get("rationale", "")
    logger.info(f"LLM selected test: {test_name}, variables: {variables}")

    # If LLM declared unsupported, return politely
    if test_name == UNSUPPORTED_TEST:
        return _unsupported_analysis_result(
            question,
            message=selection.get("message", ""),
            rationale=rationale,
            alpha=alpha,
        )

    # Guard: if LLM somehow chose a non-active test, treat as unsupported
    if test_name not in SUPPORTED_TESTS:
        logger.warning(f"LLM chose inactive test '{test_name}'; returning unsupported.")
        return _unsupported_analysis_result(
            question,
            message=(
                f"The test '{test_name}' is not currently available. "
                "Please see the list of supported analyses."
            ),
            rationale=rationale,
            alpha=alpha,
        )

    # Step 2: Normalize and validate variables
    try:
        test_name, variables = normalize_test_selection(df, test_name, variables, question)
        logger.info(f"After normalization: {test_name}, variables: {variables}")
    except StatisticalAnalysisError as exc:
        logger.warning(f"Normalization rejected (returning unsupported): {exc}")
        return _unsupported_analysis_result(
            question,
            message=str(exc),
            rationale=str(exc),
            alpha=alpha,
        )

    # Validate that referenced columns exist in the dataframe
    for role, col in variables.items():
        if role == "popmean":
            continue
        if not isinstance(col, str):
            continue
        col_names = [c.strip() for c in col.split(",") if c.strip()] if "," in col else [col]
        for name in col_names:
            if name and name not in df.columns:
                return _unsupported_analysis_result(
                    question,
                    message=(
                        f"Column '{name}' (as '{role}') was not found in the dataset. "
                        f"Available columns: {', '.join(df.columns.tolist())}"
                    ),
                    rationale=f"Missing column '{name}'",
                    alpha=alpha,
                )

    # Step 3: Run the test
    runner = TEST_RUNNERS.get(test_name)
    if runner is None:
        return _unsupported_analysis_result(
            question,
            message=f"No runner is implemented for test '{test_name}'.",
            rationale="Missing runner",
            alpha=alpha,
        )

    logger.info(f"Running {test_name}...")
    try:
        raw_results = runner(df, variables)
    except StatisticalAnalysisError as exc:
        logger.warning(f"Test runner rejected (returning unsupported): {exc}")
        return _unsupported_analysis_result(
            question,
            message=str(exc),
            rationale=str(exc),
            alpha=alpha,
        )
    except Exception as exc:
        logger.error(f"Unexpected error in test runner: {exc}\n{traceback.format_exc()}")
        return _unsupported_analysis_result(
            question,
            message=(
                "An unexpected error occurred while running the statistical test. "
                "Please verify your data is clean and well-formatted, then try again."
            ),
            rationale=str(exc),
            alpha=alpha,
        )

    # Step 4: LLM explains results
    logger.info("Calling LLM for explanation...")
    try:
        interpretation, plain_explanation = explain_results_via_llm(
            question, test_name, variables, raw_results, alpha
        )
    except Exception as exc:
        logger.warning(f"LLM explanation failed (using fallback): {exc}")
        p_val = raw_results.get("p_value")
        sig = p_val is not None and p_val < alpha
        interpretation = (
            f"The {TEST_DISPLAY_NAMES.get(test_name, test_name)} yielded "
            f"statistic={raw_results.get('statistic')}, p={p_val}. "
            f"Result is {'significant' if sig else 'not significant'} at α={alpha}."
        )
        plain_explanation = interpretation

    p_value = raw_results.get("p_value")
    significant = p_value is not None and p_value < alpha

    return {
        "test_name": test_name,
        "test_display_name": TEST_DISPLAY_NAMES.get(test_name, test_name),
        "variables_used": _format_variables_used(variables),
        "rationale": rationale,
        "statistic": raw_results.get("statistic"),
        "p_value": p_value,
        "additional_stats": raw_results.get("additional_stats", {}),
        "assumption_checks": raw_results.get("assumption_checks", []),
        "interpretation": interpretation,
        "plain_explanation": plain_explanation,
        "significant": significant,
        "alpha": alpha,
        "error": None,
    }


# ──────────────────────────────────────────────────────────────────
# Dataset-aware example question generator
# ──────────────────────────────────────────────────────────────────

def generate_valid_example_questions(df: pd.DataFrame, n: int = 6) -> List[str]:
    """
    Generate example questions that are GUARANTEED to be answerable with the
    4 active tests given the actual data.

    Strategy:
    1. Ask the LLM to generate N candidate questions using the exact same
       constraint prompt used in select_test_via_llm (so it knows the 4 tests
       and their column-type requirements).
    2. For each candidate, run select_test_via_llm on it — drop any that come
       back as "unsupported" or raise an error.
    3. If not enough valid questions survive, fill remaining slots from a
       rule-based heuristic that is guaranteed valid for this dataset.
    """
    schema_profile = profile_dataframe(df)

    # ── Step 1: identify what tests are structurally possible ─────────────
    numeric_cols = [
        c["name"] for c in schema_profile["columns"] if c.get("type") == "numeric"
    ]
    categorical_cols = [
        c for c in schema_profile["columns"]
        if c.get("type") == "categorical" and "id" not in c["name"].lower()
    ]

    # For t-test we need categoricals with exactly 2 unique values
    binary_cat_cols = [
        c["name"] for c in categorical_cols
        if c.get("unique_count", 0) == 2
    ]
    # For chi-square we need any two categoricals
    cat_col_names = [c["name"] for c in categorical_cols]

    multi_cat_cols = [
        c["name"] for c in categorical_cols
        if c.get("unique_count", 0) >= 3
    ]

    possible_tests: List[str] = []
    if len(numeric_cols) >= 2:
        possible_tests.extend(["pearson_correlation", "simple_linear_regression"])
    if numeric_cols and binary_cat_cols:
        possible_tests.append("independent_ttest")
    if len(cat_col_names) >= 2:
        possible_tests.append("chi_square")
    if numeric_cols and multi_cat_cols:
        possible_tests.append("one_way_anova")

    if not possible_tests:
        return ["No supported statistical tests can be applied to this dataset."]

    # ── Step 2: ask LLM to generate candidate questions ───────────────────
    available_tests_block = "\n".join(
        f'  "{k}": {v}' for k, v in ACTIVE_TEST_DESCRIPTIONS.items()
    )

    system_prompt = (
        "You are an expert statistician generating example questions for a statistics app.\n\n"
        "SUPPORTED TESTS — the ONLY tests this application can run:\n"
        f"{available_tests_block}\n\n"
        "DATASET SCHEMA:\n"
        f"{json.dumps(schema_profile, indent=2, default=str)}\n\n"
        "Generate EXACTLY 10 natural-language questions a user might ask about this specific "
        "dataset. Each question MUST:\n"
        "  1. Be answerable by exactly ONE of the supported tests listed above.\n"
        "  2. Reference actual column names from the schema.\n"
        "  3. Respect the column types:\n"
        "     - independent_ttest: one numeric column + one categorical column with EXACTLY 2 groups.\n"
        "     - pearson_correlation: two numeric columns.\n"
        "     - simple_linear_regression: one numeric predictor → one numeric outcome.\n"
        "     - chi_square: two categorical (non-numeric) columns.\n"
        "     - one_way_anova: one numeric outcome + one categorical column with 3 OR MORE groups.\n"
        "  4. NOT require multiple regression, logistic regression, paired tests, "
        "or any test NOT in the supported list above.\n\n"
        "Cover all 5 supported tests where the data allows.\n"
        "Return ONLY a JSON array of 10 strings — no markdown, no explanation."
    )

    candidates: List[str] = []
    try:
        client = _get_client()
        resp = client.chat.completions.create(
            model=OPENAI_CHAT_MODEL,
            messages=[{"role": "user", "content": system_prompt}],
            temperature=0.5,
            max_tokens=700,
        )
        raw = (resp.choices[0].message.content or "").strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            candidates = [str(q) for q in parsed if q]
    except Exception as exc:
        logger.warning(f"LLM example generation failed: {exc}")

    # ── Step 3: validate each candidate by dry-running the test selector ──
    # Each validation is its own OpenAI call; running them concurrently instead
    # of in a sequential loop turns ~10 * 2-3s (20-30s) into ~1 call's worth of
    # wall time.
    def _validate_candidate(q: str) -> Optional[str]:
        try:
            sel = select_test_via_llm(q, schema_profile)
            if sel.get("test") == UNSUPPORTED_TEST:
                logger.debug(f"Example question rejected (unsupported): {q}")
                return None
            test = sel.get("test")
            variables = sel.get("variables") or {}
            # Also run normalization to catch column-mismatch errors
            normalize_test_selection(df, test, variables, q)
            return q
        except Exception as exc:
            logger.debug(f"Example question failed validation ({exc}): {q}")
            return None

    valid_questions: List[str] = []
    if candidates:
        with ThreadPoolExecutor(max_workers=min(len(candidates), 10)) as pool:
            for q in pool.map(_validate_candidate, candidates):
                if q:
                    valid_questions.append(q)
    valid_questions = valid_questions[:n]

    # ── Step 4: heuristic fill-in if not enough valid questions ───────────
    if len(valid_questions) < n:
        heuristics = _heuristic_example_questions(
            numeric_cols, binary_cat_cols, cat_col_names, multi_cat_cols, schema_profile
        )
        for hq in heuristics:
            if len(valid_questions) >= n:
                break
            if hq not in valid_questions:
                valid_questions.append(hq)

    return valid_questions[:n]


def _heuristic_example_questions(
    numeric_cols: List[str],
    binary_cat_cols: List[str],
    cat_col_names: List[str],
    multi_cat_cols: List[str],
    schema_profile: Dict[str, Any],
) -> List[str]:
    """
    Build guaranteed-valid example questions from the data schema
    without any LLM call — used as fallback fill-in.
    """
    questions: List[str] = []

    # pearson_correlation — two numeric columns
    if len(numeric_cols) >= 2:
        questions.append(
            f"Is there a linear correlation between {numeric_cols[0]} and {numeric_cols[1]}?"
        )
    if len(numeric_cols) >= 3:
        questions.append(
            f"Is there a significant relationship between {numeric_cols[1]} and {numeric_cols[2]}?"
        )

    # simple_linear_regression — one numeric predicts another
    if len(numeric_cols) >= 2:
        questions.append(
            f"Does {numeric_cols[0]} predict {numeric_cols[1]}?"
        )
    if len(numeric_cols) >= 3:
        questions.append(
            f"Can we use {numeric_cols[2]} to predict {numeric_cols[0]}?"
        )

    # independent_ttest — binary categorical + numeric
    if binary_cat_cols and numeric_cols:
        questions.append(
            f"Is there a significant difference in {numeric_cols[0]} between the two {binary_cat_cols[0]} groups?"
        )
    if len(binary_cat_cols) >= 1 and len(numeric_cols) >= 2:
        questions.append(
            f"Do the two groups in {binary_cat_cols[0]} differ significantly in {numeric_cols[1]}?"
        )

    # chi_square — two categoricals
    if len(cat_col_names) >= 2:
        questions.append(
            f"Is there a significant association between {cat_col_names[0]} and {cat_col_names[1]}?"
        )
    if len(cat_col_names) >= 3:
        questions.append(
            f"Are {cat_col_names[1]} and {cat_col_names[2]} independent of each other?"
        )

    # one_way_anova — categorical grouping (3+ groups) + numeric outcome
    if multi_cat_cols and numeric_cols:
        questions.append(
            f"Does {numeric_cols[0]} differ significantly across the {multi_cat_cols[0]} groups?"
        )
    if len(multi_cat_cols) >= 1 and len(numeric_cols) >= 2:
        questions.append(
            f"Is there a significant difference in {numeric_cols[1]} between the different {multi_cat_cols[0]} groups?"
        )

    return questions