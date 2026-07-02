"""
Visualization service.
Builds the full set of Plotly charts for a completed statistical test result,
plus a short plain-language caption for each chart so non-technical users can
read the picture without needing to understand the underlying statistics.

Chart selection depends on the shape of the test:
  - independent_ttest / one_way_anova (group vs numeric outcome):
        boxplot, violin plot, overlaid normal ("bell") curves, grouped histogram
  - pearson_correlation / simple_linear_regression (numeric vs numeric):
        scatterplot with trend line, per-variable histograms, correlation matrix
  - chi_square (categorical vs categorical):
        contingency heatmap
Every suite also includes the p-value-vs-alpha significance gauge.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from scipy import stats as scipy_stats

logger = logging.getLogger(__name__)

PALETTE = ["#1e3a5f", "#2f8f6e", "#c0392b", "#d4a017", "#7a5195", "#3d7ea6", "#e67e22", "#16a085"]


def _fig_to_dict(fig: go.Figure) -> Dict[str, Any]:
    return json.loads(fig.to_json())


def _fmt(x: Optional[float], nd: int = 3) -> str:
    return f"{x:.{nd}f}" if isinstance(x, (int, float)) and not isinstance(x, bool) else "—"


def _chart_entry(key: str, title: str, fig: go.Figure, interpretation: str) -> Dict[str, Any]:
    return {"key": key, "title": title, "figure": _fig_to_dict(fig), "interpretation": interpretation}


def _base_layout(fig: go.Figure, height: int = 380) -> None:
    fig.update_layout(
        height=height,
        margin=dict(l=40, r=20, t=50, b=30),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )


# ── Significance gauge ──────────────────────────────────────────────

def build_gauge_chart(p_value: Optional[float], alpha: float, test_name: str) -> go.Figure:
    """Interactive gauge mapping the p-value against the alpha threshold."""
    if p_value is None:
        fig = go.Figure()
        fig.update_layout(title="No visual data available for this analysis type.")
        return fig

    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=p_value,
        delta={'reference': alpha, 'position': "top", 'relative': False, 'valueformat': '.4f'},
        domain={'x': [0, 1], 'y': [0, 1]},
        title={'text': f"p-value vs Alpha ({alpha})", 'font': {'size': 16, 'color': "#1e3a5f"}},
        gauge={
            'axis': {'range': [0, max(alpha * 2, min(1.0, p_value * 1.2, 0.2))], 'tickformat': '.3f'},
            'bar': {'color': "#1e3a5f", 'thickness': 0.25},
            'bgcolor': "white",
            'borderwidth': 1,
            'bordercolor': "#d4e2ef",
            'steps': [
                {'range': [0, alpha], 'color': '#e6f4ec'},
                {'range': [alpha, 1.0], 'color': '#fdecea'},
            ],
            'threshold': {'line': {'color': "red", 'width': 3}, 'thickness': 0.75, 'value': alpha},
        },
    ))
    fig.update_layout(
        height=260,
        margin=dict(l=30, r=30, t=40, b=20),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
    )
    return fig


def _interp_gauge(p_value: Optional[float], alpha: float) -> str:
    if p_value is None:
        return "No p-value was produced for this analysis, so there is nothing to compare against alpha."
    if p_value < alpha:
        return (
            f"The p-value ({_fmt(p_value, 4)}) falls left of the red threshold line, inside the green zone. "
            f"That means the result is unlikely to be due to chance alone (below the α = {alpha} cutoff), "
            "so we call this statistically significant."
        )
    return (
        f"The p-value ({_fmt(p_value, 4)}) falls right of the red threshold line, inside the red zone. "
        f"That means the observed effect could plausibly be due to random chance (above the α = {alpha} cutoff), "
        "so we do not call this statistically significant."
    )


# ── Boxplot / violin (group vs numeric) ─────────────────────────────

def _group_series(df: pd.DataFrame, group_col: str, value_col: str) -> Dict[Any, pd.Series]:
    out: Dict[Any, pd.Series] = {}
    for g, sub in df.groupby(group_col):
        vals = pd.to_numeric(sub[value_col], errors="coerce").dropna()
        if len(vals):
            out[g] = vals
    return out


def build_boxplot(df: pd.DataFrame, group_col: str, value_col: str) -> go.Figure:
    fig = go.Figure()
    for i, (g, vals) in enumerate(_group_series(df, group_col, value_col).items()):
        fig.add_trace(go.Box(
            y=vals, name=str(g), boxmean=True,
            marker_color=PALETTE[i % len(PALETTE)],
        ))
    fig.update_layout(title=f"{value_col} by {group_col}", yaxis_title=value_col)
    _base_layout(fig)
    return fig


def build_violin_plot(df: pd.DataFrame, group_col: str, value_col: str) -> go.Figure:
    fig = go.Figure()
    for i, (g, vals) in enumerate(_group_series(df, group_col, value_col).items()):
        fig.add_trace(go.Violin(
            y=vals, name=str(g), box_visible=True, meanline_visible=True, points="outliers",
            line_color=PALETTE[i % len(PALETTE)],
        ))
    fig.update_layout(title=f"{value_col} distribution shape by {group_col}", yaxis_title=value_col)
    _base_layout(fig)
    return fig


def _interp_group_spread(df: pd.DataFrame, group_col: str, value_col: str, chart_kind: str) -> str:
    groups = _group_series(df, group_col, value_col)
    if len(groups) < 2:
        return f"Shows how {value_col} is distributed within each {group_col} group."
    means = {g: v.mean() for g, v in groups.items()}
    top = max(means, key=means.get)
    bottom = min(means, key=means.get)
    shape_note = (
        "The box marks the middle 50% of values, the line inside is the median, and the diamond is the mean."
        if chart_kind == "box"
        else "The width at each height shows how common that value is; the inner box marks the median and quartiles."
    )
    return (
        f"'{top}' has the highest average {value_col} ({_fmt(means[top], 2)}), while '{bottom}' has the lowest "
        f"({_fmt(means[bottom], 2)}). {shape_note} The more the shapes overlap, the less likely the groups "
        "genuinely differ; the less they overlap, the stronger the visual evidence of a real difference."
    )


# ── Bell curves (normal approximation per group) ────────────────────

def build_bell_curves(df: pd.DataFrame, group_col: str, value_col: str) -> go.Figure:
    groups = _group_series(df, group_col, value_col)
    all_vals = pd.concat(groups.values()) if groups else pd.Series(dtype=float)
    if all_vals.empty:
        fig = go.Figure()
        fig.update_layout(title="No data available for bell curve.")
        return fig

    pad = (all_vals.max() - all_vals.min()) * 0.25 or 1.0
    x = np.linspace(all_vals.min() - pad, all_vals.max() + pad, 300)

    fig = go.Figure()
    for i, (g, vals) in enumerate(groups.items()):
        mu, sigma = float(vals.mean()), float(vals.std(ddof=1)) if len(vals) > 1 else 0.0
        if sigma == 0:
            continue
        y = scipy_stats.norm.pdf(x, mu, sigma)
        color = PALETTE[i % len(PALETTE)]
        fig.add_trace(go.Scatter(
            x=x, y=y, mode="lines", name=f"{g} (μ={mu:.2f}, σ={sigma:.2f})",
            line=dict(color=color, width=2), fill="tozeroy", opacity=0.5,
        ))
        fig.add_vline(x=mu, line=dict(color=color, dash="dash", width=1))

    fig.update_layout(
        title=f"Normal (bell curve) approximation of {value_col} by {group_col}",
        xaxis_title=value_col, yaxis_title="Probability density",
    )
    _base_layout(fig)
    return fig


def _interp_bell_curves(df: pd.DataFrame, group_col: str, value_col: str, p_value: Optional[float], alpha: float) -> str:
    groups = _group_series(df, group_col, value_col)
    overlap_note = "heavily overlap" if len(groups) >= 2 else "is shown"
    sig_note = ""
    if p_value is not None:
        sig_note = (
            " This lines up with the test result: " + (
                "the curves are separated enough that the difference is unlikely to be chance."
                if p_value < alpha else
                "the curves overlap enough that the difference could plausibly be chance."
            )
        )
    return (
        f"Each bell-shaped curve is an idealized picture of one {group_col} group's {value_col} values, built "
        f"from that group's own average (dashed line) and spread. Curves that sit far apart with little overlap "
        f"suggest a real difference between groups; curves that {overlap_note} suggest the groups look similar." + sig_note
    )


# ── Histograms ───────────────────────────────────────────────────────

def build_histogram(df: pd.DataFrame, value_col: str, group_col: Optional[str] = None) -> go.Figure:
    fig = go.Figure()
    if group_col and group_col in df.columns:
        for i, (g, vals) in enumerate(_group_series(df, group_col, value_col).items()):
            fig.add_trace(go.Histogram(
                x=vals, name=str(g), opacity=0.6, marker_color=PALETTE[i % len(PALETTE)],
            ))
        fig.update_layout(barmode="overlay", title=f"Distribution of {value_col} by {group_col}")
    else:
        vals = pd.to_numeric(df[value_col], errors="coerce").dropna()
        fig.add_trace(go.Histogram(x=vals, marker_color=PALETTE[0], name=value_col))
        fig.update_layout(title=f"Distribution of {value_col}")
    fig.update_layout(xaxis_title=value_col, yaxis_title="Count")
    _base_layout(fig)
    return fig


def _interp_histogram(df: pd.DataFrame, value_col: str) -> str:
    vals = pd.to_numeric(df[value_col], errors="coerce").dropna()
    if vals.empty:
        return f"Shows how often each range of {value_col} values occurs."
    skew = float(vals.skew())
    shape = (
        "roughly symmetric (bell-shaped)" if abs(skew) < 0.5 else
        "skewed toward higher values (a longer tail on the right)" if skew > 0 else
        "skewed toward lower values (a longer tail on the left)"
    )
    return (
        f"Each bar counts how many rows fall into that range of {value_col}. The shape here is {shape}, "
        f"centered around {_fmt(vals.mean(), 2)}. This is a quick visual check of the 'normal distribution' "
        "assumption many statistical tests rely on."
    )


# ── Scatterplot + correlation matrix (numeric vs numeric) ───────────

def build_scatterplot(df: pd.DataFrame, x_col: str, y_col: str) -> go.Figure:
    clean = df[[x_col, y_col]].apply(pd.to_numeric, errors="coerce").dropna()
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=clean[x_col], y=clean[y_col], mode="markers", name="Observations",
        marker=dict(color=PALETTE[0], size=8, opacity=0.7),
    ))
    if len(clean) >= 2 and clean[x_col].std() > 0:
        slope, intercept = np.polyfit(clean[x_col], clean[y_col], 1)
        x_line = np.linspace(clean[x_col].min(), clean[x_col].max(), 50)
        fig.add_trace(go.Scatter(
            x=x_line, y=slope * x_line + intercept, mode="lines", name="Trend line",
            line=dict(color=PALETTE[2], width=2, dash="dash"),
        ))
    fig.update_layout(title=f"{y_col} vs {x_col}", xaxis_title=x_col, yaxis_title=y_col)
    _base_layout(fig)
    return fig


def _interp_scatter(df: pd.DataFrame, x_col: str, y_col: str) -> str:
    clean = df[[x_col, y_col]].apply(pd.to_numeric, errors="coerce").dropna()
    if len(clean) < 3 or clean[x_col].std() == 0 or clean[y_col].std() == 0:
        return f"Each point is one observation, plotting {x_col} against {y_col}."
    r = float(clean[x_col].corr(clean[y_col]))
    strength = (
        "very strong" if abs(r) >= 0.8 else "strong" if abs(r) >= 0.6 else
        "moderate" if abs(r) >= 0.4 else "weak" if abs(r) >= 0.2 else "negligible"
    )
    direction = "increase together" if r > 0 else "move in opposite directions"
    return (
        f"Each point is one row of data. The dashed trend line summarizes the overall pattern: as {x_col} goes up, "
        f"{y_col} tends to {direction} ({strength} relationship, r = {_fmt(r, 3)}). The tighter the points hug the "
        "line, the more reliable the relationship."
    )


def build_correlation_matrix(df: pd.DataFrame, max_cols: int = 15) -> Optional[go.Figure]:
    numeric_df = df.select_dtypes(include=[np.number])
    if numeric_df.shape[1] < 2:
        return None
    numeric_df = numeric_df.iloc[:, :max_cols]
    corr = numeric_df.corr(method="pearson").round(2)
    fig = go.Figure(go.Heatmap(
        z=corr.values, x=corr.columns.tolist(), y=corr.columns.tolist(),
        zmin=-1, zmax=1, colorscale="RdBu", reversescale=True,
        text=corr.values, texttemplate="%{text}", colorbar=dict(title="r"),
    ))
    fig.update_layout(title="Correlation matrix (all numeric columns)")
    _base_layout(fig, height=max(380, 40 * len(corr.columns)))
    return fig


def _interp_correlation_matrix(df: pd.DataFrame, max_cols: int = 15) -> str:
    numeric_df = df.select_dtypes(include=[np.number]).iloc[:, :max_cols]
    corr = numeric_df.corr(method="pearson")
    pairs = corr.where(~np.eye(len(corr), dtype=bool)).abs().unstack().dropna()
    if pairs.empty:
        return "Each cell shows how strongly two numeric variables move together, from -1 to +1."
    (a, b), strongest = pairs.idxmax(), pairs.max()
    r_signed = corr.loc[a, b]
    return (
        "Each cell shows how strongly two numeric variables move together, from -1 (perfect opposite) to "
        "+1 (perfectly together); 0 means no linear relationship. Darker red = strong positive, darker blue = "
        f"strong negative. The strongest relationship here is between '{a}' and '{b}' (r = {_fmt(r_signed, 2)})."
    )


# ── Chi-square contingency heatmap ───────────────────────────────────

def build_contingency_heatmap(df: pd.DataFrame, x_col: str, y_col: str) -> go.Figure:
    ct = pd.crosstab(df[x_col], df[y_col])
    fig = go.Figure(go.Heatmap(
        z=ct.values, x=[str(c) for c in ct.columns], y=[str(i) for i in ct.index],
        colorscale="Blues", text=ct.values, texttemplate="%{text}", colorbar=dict(title="Count"),
    ))
    fig.update_layout(title=f"{x_col} vs {y_col} (observed counts)", xaxis_title=y_col, yaxis_title=x_col)
    _base_layout(fig)
    return fig


def _interp_contingency(df: pd.DataFrame, x_col: str, y_col: str) -> str:
    ct = pd.crosstab(df[x_col], df[y_col])
    if ct.empty:
        return f"Shows how often each combination of {x_col} and {y_col} occurs."
    max_idx = np.unravel_index(np.argmax(ct.values), ct.values.shape)
    row_label, col_label = ct.index[max_idx[0]], ct.columns[max_idx[1]]
    return (
        f"Each cell counts how many rows have that combination of {x_col} and {y_col}. The most common "
        f"combination is '{row_label}' with '{col_label}' ({int(ct.values[max_idx])} rows). If the counts were "
        "spread out proportionally across rows and columns, the two variables would be independent — uneven "
        "cells like this are what drives a significant chi-square result."
    )


# ── Orchestrator ──────────────────────────────────────────────────────

GROUP_VALUE_TESTS = {"independent_ttest", "one_way_anova"}
NUMERIC_PAIR_TESTS = {"pearson_correlation", "simple_linear_regression"}


def build_visualization_suite(
    df: pd.DataFrame,
    test_name: str,
    variables_used: Dict[str, str],
    p_value: Optional[float],
    alpha: float,
) -> List[Dict[str, Any]]:
    charts: List[Dict[str, Any]] = [
        _chart_entry(
            "gauge", "Significance gauge: p-value vs alpha",
            build_gauge_chart(p_value, alpha, test_name),
            _interp_gauge(p_value, alpha),
        )
    ]

    group_col = variables_used.get("group") or variables_used.get("x")
    value_col = variables_used.get("y")
    x_col = variables_used.get("x")
    y_col = variables_used.get("y")

    try:
        if test_name in GROUP_VALUE_TESTS and group_col in df.columns and value_col in df.columns:
            charts.append(_chart_entry(
                "boxplot", f"Boxplot: {value_col} by {group_col}",
                build_boxplot(df, group_col, value_col),
                _interp_group_spread(df, group_col, value_col, "box"),
            ))
            charts.append(_chart_entry(
                "violin", f"Violin plot: {value_col} by {group_col}",
                build_violin_plot(df, group_col, value_col),
                _interp_group_spread(df, group_col, value_col, "violin"),
            ))
            charts.append(_chart_entry(
                "bell_curve", "Bell curve comparison",
                build_bell_curves(df, group_col, value_col),
                _interp_bell_curves(df, group_col, value_col, p_value, alpha),
            ))
            charts.append(_chart_entry(
                "histogram", f"Histogram: {value_col} by {group_col}",
                build_histogram(df, value_col, group_col),
                _interp_histogram(df, value_col),
            ))

        elif test_name in NUMERIC_PAIR_TESTS and x_col in df.columns and y_col in df.columns:
            charts.append(_chart_entry(
                "scatter", f"Scatterplot: {y_col} vs {x_col}",
                build_scatterplot(df, x_col, y_col),
                _interp_scatter(df, x_col, y_col),
            ))
            charts.append(_chart_entry(
                "histogram_x", f"Histogram: {x_col}",
                build_histogram(df, x_col),
                _interp_histogram(df, x_col),
            ))
            charts.append(_chart_entry(
                "histogram_y", f"Histogram: {y_col}",
                build_histogram(df, y_col),
                _interp_histogram(df, y_col),
            ))
            corr_fig = build_correlation_matrix(df)
            if corr_fig is not None:
                charts.append(_chart_entry(
                    "correlation_matrix", "Correlation matrix",
                    corr_fig, _interp_correlation_matrix(df),
                ))

        elif test_name == "chi_square" and x_col in df.columns and y_col in df.columns:
            charts.append(_chart_entry(
                "contingency", f"Contingency heatmap: {x_col} vs {y_col}",
                build_contingency_heatmap(df, x_col, y_col),
                _interp_contingency(df, x_col, y_col),
            ))
    except Exception as exc:
        logger.warning(f"Visualization suite: skipping extra charts after error: {exc}")

    return charts
