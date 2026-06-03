"""
Streamlit frontend for the Statistical Hypothesis Testing Assistant.
"""

import html
import json
import time
from io import BytesIO
from typing import Any, Dict, List, Optional

import pandas as pd
import requests
import streamlit as st

# ── Configuration ─────────────────────────────────────────────────
BACKEND_URL = "http://localhost:8000"


def backend(method: str, path: str, **kwargs) -> Optional[Dict]:
    """Make a request to the backend and return JSON or None."""
    try:
        resp = requests.request(method, f"{BACKEND_URL}{path}", timeout=120, **kwargs)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        st.error("⚠️ Cannot connect to backend. Is the FastAPI server running on port 8000?")
        return None
    except requests.exceptions.HTTPError as e:
        detail = e.response.text[:300]
        try:
            body = e.response.json()
            if isinstance(body, dict) and "detail" in body:
                detail = body["detail"] if isinstance(body["detail"], str) else str(body["detail"])
        except Exception:
            pass
        st.error(f"Backend error ({e.response.status_code}): {detail}")
        return None
    except Exception as e:
        st.error(f"Unexpected error: {e}")
        return None


# ── Page config ───────────────────────────────────────────────────
st.set_page_config(
    page_title="Statistical Hypothesis Testing Assistant",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Session state initialisation ─────────────────────────────────
for key, default in {
    "pdf_uploaded": False,
    "pdf_filename": "",
    "csv_session_id": None,
    "csv_filename": "",
    "csv_columns": [],
    "csv_dtypes": {},
    "csv_preview": [],
    "csv_rows": 0,
    "chat_history": [],
    "stats_history": [],
    "example_questions": [],
    "stat_question": "",
    "qa_pending_question": None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default


PDF_QA_PROMPTS = [
    "What is the main research question or objective?",
    "What methodology or study design was used?",
    "Summarize the key findings in a few sentences.",
    "What limitations does the author discuss?",
]


def generate_example_questions(session_id: str, columns: list, dtypes: dict) -> list:
    """
    Fetch dataset-specific example questions from the backend.
    The backend validates each question against the 4 supported tests AND
    the actual data before returning — so every question shown is guaranteed
    to be runnable without an 'unsupported' error.

    Falls back to a local heuristic if the backend call fails.
    """
    result = backend("POST", "/stats/examples", json={"session_id": session_id, "n": 6})
    if result and result.get("questions"):
        return result["questions"]

    # ── Local heuristic fallback ──────────────────────────────────────────
    # Only generates questions for the 4 supported tests using column types.
    numeric_cols = [c for c, d in dtypes.items() if "int" in d or "float" in d]
    binary_cat_cols = []  # we don't have unique counts here, so skip t-test heuristic
    cat_cols = [
        c for c, d in dtypes.items()
        if "int" not in d and "float" not in d and "id" not in c.lower()
    ]

    questions: List[str] = []
    # pearson_correlation
    if len(numeric_cols) >= 2:
        questions.append(f"Is there a linear correlation between {numeric_cols[0]} and {numeric_cols[1]}?")
    # simple_linear_regression
    if len(numeric_cols) >= 2:
        questions.append(f"Does {numeric_cols[0]} predict {numeric_cols[1]}?")
    # chi_square
    if len(cat_cols) >= 2:
        questions.append(f"Is there a significant association between {cat_cols[0]} and {cat_cols[1]}?")
    if len(cat_cols) >= 3:
        questions.append(f"Are {cat_cols[1]} and {cat_cols[2]} statistically independent?")
    # more correlation / regression
    if len(numeric_cols) >= 3:
        questions.append(f"Is there a relationship between {numeric_cols[1]} and {numeric_cols[2]}?")
        questions.append(f"Can {numeric_cols[2]} be predicted from {numeric_cols[0]}?")

    return questions[:6] if questions else ["Ask a statistical question about your dataset."]


def _format_source_excerpt(text: str, max_len: int = 420) -> str:
    text = (text or "").strip()
    if len(text) > max_len:
        text = text[:max_len].rstrip() + "…"
    return html.escape(text)


def _relevance_percent(score: float) -> int:
    return min(100, max(0, int(float(score) * 100)))


def render_source_cards(sources: List[Dict[str, Any]], *, expanded: bool = False) -> None:
    """Render numbered citation cards with relevance bars."""
    if not sources:
        return
    label = "citation" if len(sources) == 1 else "citations"
    with st.expander(f"📎 {len(sources)} document {label}", expanded=expanded):
        for i, src in enumerate(sources, 1):
            pct = _relevance_percent(src.get("score", 0))
            excerpt = _format_source_excerpt(src.get("text", ""))
            st.markdown(
                f"""
                <div class="qa-source-card">
                    <div class="qa-source-header">
                        <span class="qa-citation-badge">{i}</span>
                        <span class="qa-relevance-text">Match</span>
                        <div class="qa-relevance-track" title="Retrieval relevance">
                            <div class="qa-relevance-fill" style="width:{pct}%;"></div>
                        </div>
                        <span class="qa-relevance-pct">{pct}%</span>
                    </div>
                    <p class="qa-source-excerpt">{excerpt}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )


def render_stats_result(result: Dict[str, Any]) -> None:
    """Render a statistical analysis result in a structured, professional layout."""
    test_name = html.escape(str(result.get("test_display_name", "Analysis")))
    rationale = html.escape(str(result.get("rationale", "")))
    interpretation = result.get("interpretation", "—")
    plain = result.get("plain_explanation", "—")

    sig = result.get("significant")
    if sig is True:
        sig_html = '<div class="stats-sig-pill stats-sig-yes">Statistically significant</div>'
    elif sig is False:
        sig_html = '<div class="stats-sig-pill stats-sig-no">Not significant</div>'
    else:
        sig_html = '<div class="stats-sig-pill stats-sig-neutral">Significance N/A</div>'

    p_val = result.get("p_value")
    p_display = f"{p_val:.4f}" if p_val is not None else "—"
    stat_val = result.get("statistic")
    stat_display = f"{stat_val:.4f}" if stat_val is not None else "—"
    alpha = result.get("alpha", 0.05)

    with st.container(border=True):
        st.markdown(
            f"""
            <div class="stats-results-header">
                <div class="stats-results-title">
                    <span class="stats-test-badge">{test_name}</span>
                    {sig_html}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        kpi_items = [
            ("p-value", p_display),
            ("Test statistic", stat_display),
            ("α (alpha)", str(alpha)),
        ]
        add = dict(result.get("additional_stats") or {})
        if "n" in add:
            kpi_items.append(("Sample size (n)", str(add["n"])))
        if "r_squared" in add:
            kpi_items.append(("R²", str(add["r_squared"])))
        if "pseudo_r_squared" in add:
            kpi_items.append(("Pseudo R²", str(add["pseudo_r_squared"])))

        kpi_html = '<div class="stats-kpi-row">'
        for label, value in kpi_items[:6]:
            kpi_html += (
                f'<div class="stats-kpi-card">'
                f'<span class="stats-kpi-label">{html.escape(label)}</span>'
                f'<span class="stats-kpi-value">{html.escape(value)}</span>'
                f"</div>"
            )
        kpi_html += "</div>"
        st.markdown(kpi_html, unsafe_allow_html=True)

        if rationale:
            st.markdown(
                f'<div class="stats-rationale-box"><strong>Why this test?</strong> {rationale}</div>',
                unsafe_allow_html=True,
            )

        variables = result.get("variables_used") or {}
        if variables:
            chips = "".join(
                f'<span class="stats-var-chip">'
                f'<span class="stats-var-role">{html.escape(role)}</span>'
                f'{html.escape(str(col))}</span>'
                for role, col in variables.items()
            )
            st.markdown(
                f'<p class="stats-section-label">Variables</p><div class="stats-var-row">{chips}</div>',
                unsafe_allow_html=True,
            )

        if add:
            with st.expander("Detailed statistics", expanded=False):
                add_copy = dict(add)
                if "contingency_table" in add_copy:
                    st.dataframe(pd.DataFrame(add_copy.pop("contingency_table")), use_container_width=True)
                if "coefficients" in add_copy:
                    st.dataframe(pd.DataFrame(add_copy.pop("coefficients")).T, use_container_width=True)
                if "group_stats" in add_copy:
                    st.dataframe(pd.DataFrame(add_copy.pop("group_stats")).T, use_container_width=True)
                rem = {k: v for k, v in add_copy.items() if not isinstance(v, dict)}
                if rem:
                    rcols = st.columns(min(len(rem), 4))
                    for i, (k, v) in enumerate(rem.items()):
                        rcols[i % 4].metric(k.replace("_", " ").title(), str(v))

        checks = result.get("assumption_checks") or []
        if checks:
            with st.expander("Assumption checks", expanded=False):
                for check in checks:
                    passed = check.get("passed", False)
                    cls = "stats-assumption-pass" if passed else "stats-assumption-warn"
                    icon = "✓" if passed else "!"
                    st.markdown(
                        f'<div class="stats-assumption-card {cls}">'
                        f'<span class="stats-assumption-icon">{icon}</span>'
                        f'<div><strong>{html.escape(check.get("name", ""))}</strong><br>'
                        f'<span>{html.escape(check.get("detail", ""))}</span></div>'
                        f"</div>",
                        unsafe_allow_html=True,
                    )

        st.markdown('<p class="stats-section-label">Interpretation</p>', unsafe_allow_html=True)
        icol1, icol2 = st.columns(2, gap="medium")
        with icol1:
            st.markdown("##### Technical")
            with st.container(border=True):
                st.markdown(interpretation)
        with icol2:
            st.markdown("##### Plain language")
            with st.container(border=True):
                st.markdown(plain)


def handle_qa_question(question: str) -> None:
    """Send a question to the PDF Q&A API and append results to chat history."""
    question = question.strip()
    if not question or not st.session_state.pdf_uploaded:
        return

    st.session_state.chat_history.append({"role": "user", "content": question})
    result = backend("POST", "/qa/ask", json={"question": question, "top_k": 5})
    if result:
        st.session_state.chat_history.append({
            "role": "assistant",
            "content": result.get("answer", "No answer returned."),
            "sources": result.get("sources", []),
        })


# ── Custom CSS ────────────────────────────────────────────────────
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(135deg, #1e3a5f 0%, #2d6a9f 100%);
        padding: 1.5rem 2rem;
        border-radius: 12px;
        margin-bottom: 1.5rem;
        color: white;
    }
    .metric-card {
        background: #f0f4f8;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #2d6a9f;
        margin: 0.5rem 0;
    }
    .test-badge {
        background: #2d6a9f;
        color: white;
        padding: 0.3rem 0.8rem;
        border-radius: 20px;
        font-size: 0.85rem;
        font-weight: 600;
    }
    .sig-yes { color: #0a7c42; font-weight: 700; }
    .sig-no  { color: #c0392b; font-weight: 700; }
    .assumption-pass { color: #0a7c42; }
    .assumption-fail { color: #e67e22; }
    .source-box {
        background: #f8f9fa;
        border-left: 3px solid #2d6a9f;
        padding: 0.6rem 1rem;
        border-radius: 4px;
        margin: 0.4rem 0;
        font-size: 0.85rem;
        color: #444;
    }

    /* ── PDF Q&A tab ── */
    .qa-hero {
        background: linear-gradient(135deg, #1e3a5f 0%, #2d6a9f 100%);
        border-radius: 12px;
        padding: 1.25rem 1.5rem;
        margin-bottom: 1rem;
        color: #fff;
    }
    .qa-hero h3 {
        margin: 0 0 0.35rem 0;
        font-size: 1.35rem;
        font-weight: 600;
        letter-spacing: -0.02em;
    }
    .qa-hero p {
        margin: 0;
        font-size: 0.92rem;
        opacity: 0.9;
        line-height: 1.5;
    }
    .qa-doc-pill {
        display: inline-block;
        margin-top: 0.75rem;
        background: rgba(255,255,255,0.15);
        border: 1px solid rgba(255,255,255,0.25);
        padding: 0.35rem 0.85rem;
        border-radius: 999px;
        font-size: 0.82rem;
    }
    [data-testid="stVerticalBlockBorderWrapper"] {
        border-color: #d4e2ef !important;
        border-radius: 12px !important;
        box-shadow: 0 2px 12px rgba(30, 58, 95, 0.06);
        background: #ffffff;
    }
    .qa-toolbar-meta {
        color: #5a6f85;
        font-size: 0.85rem;
        margin: 0;
        padding-top: 0.35rem;
    }
    .qa-empty-state {
        text-align: center;
        padding: 2.5rem 1.5rem;
        background: #f0f4f8;
        border: 1px dashed #b8cfe0;
        border-radius: 12px;
        margin: 0.5rem 0 1rem;
    }
    .qa-empty-state h4 {
        color: #1e3a5f;
        margin: 0 0 0.5rem;
        font-size: 1.1rem;
    }
    .qa-empty-state p {
        color: #5a6f85;
        margin: 0 0 1rem;
        font-size: 0.9rem;
        max-width: 32rem;
        margin-left: auto;
        margin-right: auto;
        line-height: 1.55;
    }
    .qa-steps {
        display: inline-block;
        text-align: left;
        color: #3d5166;
        font-size: 0.88rem;
        line-height: 1.8;
        margin: 0;
        padding-left: 1.2rem;
    }
    .qa-welcome {
        background: #f0f4f8;
        border-left: 4px solid #2d6a9f;
        border-radius: 0 10px 10px 0;
        padding: 1rem 1.15rem;
        margin-bottom: 1rem;
        color: #3d5166;
        font-size: 0.9rem;
        line-height: 1.55;
    }
    .qa-welcome strong { color: #1e3a5f; }
    .qa-prompt-label {
        color: #1e3a5f;
        font-size: 0.8rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        margin: 0.75rem 0 0.5rem;
    }
    .qa-source-card {
        background: #f8fafc;
        border: 1px solid #e2ebf3;
        border-left: 4px solid #2d6a9f;
        border-radius: 8px;
        padding: 0.85rem 1rem;
        margin-bottom: 0.65rem;
    }
    .qa-source-header {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        margin-bottom: 0.5rem;
        flex-wrap: wrap;
    }
    .qa-citation-badge {
        background: #2d6a9f;
        color: #fff;
        font-size: 0.72rem;
        font-weight: 700;
        min-width: 1.5rem;
        height: 1.5rem;
        line-height: 1.5rem;
        text-align: center;
        border-radius: 6px;
    }
    .qa-relevance-text {
        font-size: 0.72rem;
        color: #5a6f85;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }
    .qa-relevance-track {
        flex: 1;
        min-width: 80px;
        max-width: 140px;
        height: 6px;
        background: #dde8f0;
        border-radius: 999px;
        overflow: hidden;
    }
    .qa-relevance-fill {
        height: 100%;
        background: linear-gradient(90deg, #2d6a9f, #4a8fc7);
        border-radius: 999px;
    }
    .qa-relevance-pct {
        font-size: 0.75rem;
        color: #2d6a9f;
        font-weight: 600;
        min-width: 2.2rem;
    }
    .qa-source-excerpt {
        margin: 0;
        font-size: 0.88rem;
        line-height: 1.6;
        color: #3d5166;
    }
    div[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) {
        background: #f8fafc;
        border: 1px solid #e8eef4;
        border-radius: 12px;
    }

    /* ── Statistical Analysis tab ── */
    .stats-hero {
        background: linear-gradient(135deg, #1e3a5f 0%, #2d6a9f 100%);
        border-radius: 12px;
        padding: 1.25rem 1.5rem;
        margin-bottom: 1rem;
        color: #fff;
    }
    .stats-hero h3 { margin: 0 0 0.35rem; font-size: 1.35rem; font-weight: 600; }
    .stats-hero p { margin: 0; font-size: 0.92rem; opacity: 0.9; line-height: 1.5; }
    .stats-dataset-pill {
        display: inline-block;
        margin-top: 0.75rem;
        background: rgba(255,255,255,0.15);
        border: 1px solid rgba(255,255,255,0.25);
        padding: 0.35rem 0.85rem;
        border-radius: 999px;
        font-size: 0.82rem;
    }
    .stats-empty-state {
        text-align: center;
        padding: 2.5rem 1.5rem;
        background: #f0f4f8;
        border: 1px dashed #b8cfe0;
        border-radius: 12px;
        margin: 0.5rem 0 1rem;
    }
    .stats-empty-state h4 { color: #1e3a5f; margin: 0 0 0.5rem; }
    .stats-empty-state p { color: #5a6f85; margin: 0 0 1rem; font-size: 0.9rem; }
    .stats-empty-state ol {
        display: inline-block; text-align: left; color: #3d5166;
        font-size: 0.88rem; line-height: 1.8; margin: 0; padding-left: 1.2rem;
    }
    .stats-section-label {
        color: #1e3a5f;
        font-size: 0.78rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.07em;
        margin: 1rem 0 0.5rem;
    }
    .stats-input-hint {
        color: #5a6f85;
        font-size: 0.88rem;
        margin: 0 0 0.75rem;
        line-height: 1.5;
    }
    .stats-results-panel {
        background: #fff;
        border: 1px solid #d4e2ef;
        border-radius: 12px;
        padding: 1.25rem 1.35rem;
        margin-top: 1.25rem;
        box-shadow: 0 4px 16px rgba(30, 58, 95, 0.08);
    }
    .stats-results-header { margin-bottom: 1rem; }
    .stats-results-title {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: 0.65rem;
    }
    .stats-test-badge {
        background: #2d6a9f;
        color: #fff;
        padding: 0.4rem 0.95rem;
        border-radius: 8px;
        font-size: 0.95rem;
        font-weight: 600;
    }
    .stats-sig-pill {
        padding: 0.35rem 0.85rem;
        border-radius: 999px;
        font-size: 0.8rem;
        font-weight: 700;
        letter-spacing: 0.02em;
    }
    .stats-sig-yes { background: #e6f4ec; color: #0a7c42; border: 1px solid #b8e6cc; }
    .stats-sig-no { background: #fdecea; color: #c0392b; border: 1px solid #f5c6c0; }
    .stats-sig-neutral { background: #f0f4f8; color: #5a6f85; border: 1px solid #d4e2ef; }
    .stats-kpi-row {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
        gap: 0.65rem;
        margin-bottom: 1rem;
    }
    .stats-kpi-card {
        background: #f0f4f8;
        border: 1px solid #e2ebf3;
        border-radius: 10px;
        padding: 0.75rem 0.9rem;
        border-left: 4px solid #2d6a9f;
    }
    .stats-kpi-label {
        display: block;
        font-size: 0.72rem;
        color: #5a6f85;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        font-weight: 600;
        margin-bottom: 0.25rem;
    }
    .stats-kpi-value {
        display: block;
        font-size: 1.25rem;
        font-weight: 700;
        color: #1e3a5f;
    }
    .stats-rationale-box {
        background: #f0f7fc;
        border: 1px solid #c5d8e8;
        border-left: 4px solid #2d6a9f;
        border-radius: 0 10px 10px 0;
        padding: 0.9rem 1.1rem;
        color: #3d5166;
        font-size: 0.9rem;
        line-height: 1.55;
        margin-bottom: 0.5rem;
    }
    .stats-var-row { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 0.5rem; }
    .stats-var-chip {
        background: #fff;
        border: 1px solid #c5d8e8;
        border-radius: 8px;
        padding: 0.35rem 0.7rem;
        font-size: 0.85rem;
        color: #1e3a5f;
    }
    .stats-var-role {
        color: #5a6f85;
        font-size: 0.72rem;
        text-transform: uppercase;
        font-weight: 600;
        margin-right: 0.35rem;
    }
    .stats-assumption-card {
        display: flex;
        gap: 0.65rem;
        align-items: flex-start;
        padding: 0.7rem 0.9rem;
        border-radius: 8px;
        margin-bottom: 0.5rem;
        font-size: 0.88rem;
        line-height: 1.45;
    }
    .stats-assumption-pass { background: #e6f4ec; border: 1px solid #b8e6cc; color: #2d5a40; }
    .stats-assumption-warn { background: #fef6e8; border: 1px solid #f0d9a8; color: #7a5a1a; }
    .stats-assumption-icon {
        font-weight: 700;
        width: 1.25rem;
        height: 1.25rem;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        flex-shrink: 0;
        background: rgba(255,255,255,0.6);
    }
    .stats-unsupported-box {
        background: #fef6e8;
        border: 1px solid #f0d9a8;
        border-left: 4px solid #e67e22;
        border-radius: 0 10px 10px 0;
        padding: 1rem 1.15rem;
        color: #5a4a2a;
        line-height: 1.55;
        margin-top: 1rem;
    }
    .stats-error-box {
        background: #fdecea;
        border: 1px solid #f5c6c0;
        border-left: 4px solid #c0392b;
        border-radius: 0 10px 10px 0;
        padding: 1rem 1.15rem;
        color: #6b2d28;
        line-height: 1.55;
        margin-top: 1rem;
    }
    .stats-history-item {
        color: #5a6f85;
        font-size: 0.85rem;
        margin-bottom: 0.35rem;
    }
    .stats-example-row [data-testid="column"] button {
        min-height: 3.1rem;
        white-space: normal !important;
        line-height: 1.35 !important;
        text-align: left !important;
    }
    [data-testid="stVerticalBlock"]:has([data-testid="stSelectbox"]) [data-testid="stHorizontalBlock"] {
        align-items: flex-end;
    }
    [data-testid="stVerticalBlock"]:has([data-testid="stSelectbox"]) [data-testid="stHorizontalBlock"] button {
        margin-top: 0;
        min-height: 2.5rem;
    }

    div[data-testid="stSidebar"] { background: #1a2b42; }
    div[data-testid="stSidebar"] * { color: #e8edf5 !important; }
    div[data-testid="stSidebar"] .stFileUploader label { color: #b0c4de !important; }
</style>
""", unsafe_allow_html=True)


# ── Header ────────────────────────────────────────────────────────
st.markdown("""
<div class="main-header">
    <h1 style="margin:0;font-size:1.8rem;">📊 Statistical Hypothesis Testing Assistant</h1>
    <p style="margin:0.3rem 0 0;opacity:0.85;font-size:0.95rem;">
        Upload a research PDF and/or a dataset — ask questions in plain language.
        The LLM selects and runs the right statistical test automatically.
    </p>
</div>
""", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════
# SIDEBAR — Uploads
# ════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("## 📁 Upload Files")

    # ── PDF (optional) ───────────────────────────────────────────
    st.markdown("### 📄 Research PDF *(optional)*")
    pdf_file = st.file_uploader(
        "Upload a strategy/research PDF",
        type=["pdf"],
        key="pdf_uploader",
        help="The PDF will be indexed for Q&A. Useful for methodology papers.",
    )

    if pdf_file and not st.session_state.pdf_uploaded:
        with st.spinner("Parsing and indexing PDF…"):
            result = backend(
                "POST", "/upload/pdf",
                files={"file": (pdf_file.name, pdf_file.getvalue(), "application/pdf")},
            )
        if result and result.get("success"):
            st.session_state.pdf_uploaded = True
            st.session_state.pdf_filename = pdf_file.name
            st.success(f"✅ {result.get('chunks_created', 0)} chunks indexed")
        elif result:
            st.error(result.get("message", "Upload failed"))

    if st.session_state.pdf_uploaded:
        st.markdown(f"✅ **{st.session_state.pdf_filename}** indexed")
        if st.button("Remove PDF"):
            st.session_state.pdf_uploaded = False
            st.session_state.pdf_filename = ""
            st.rerun()

    st.divider()

    # ── CSV / XLSX ────────────────────────────────────────────────
    st.markdown("### 📊 Dataset (CSV / XLSX)")
    csv_file = st.file_uploader(
        "Upload your data file",
        type=["csv", "xlsx", "xls"],
        key="csv_uploader",
    )

    if csv_file:
        fname = csv_file.name
        if fname != st.session_state.csv_filename:
            with st.spinner("Loading dataset…"):
                result = backend(
                    "POST", "/upload/csv",
                    files={"file": (fname, csv_file.getvalue(), "text/csv")},
                )
            if result and result.get("success"):
                st.session_state.csv_session_id = result["session_id"]
                st.session_state.csv_filename = fname
                st.session_state.csv_columns = result["columns"]
                st.session_state.csv_dtypes = result["dtypes"]
                st.session_state.csv_preview = result["preview"]
                st.session_state.csv_rows = result["rows"]
                # Reset examples so they get regenerated for the new dataset
                st.session_state.example_questions = []
                st.session_state.stat_question = ""
                st.success(f"✅ {result['rows']} rows × {len(result['columns'])} cols")
            elif result:
                st.error(result.get("message", "Upload failed"))

    if st.session_state.csv_session_id:
        st.markdown(f"✅ **{st.session_state.csv_filename}**")
        st.caption(f"{st.session_state.csv_rows} rows · {len(st.session_state.csv_columns)} columns")
        with st.expander("Column info"):
            for col in st.session_state.csv_columns:
                dtype = st.session_state.csv_dtypes.get(col, "")
                icon = "🔢" if "int" in dtype or "float" in dtype else "🔤"
                st.caption(f"{icon} `{col}` — {dtype}")

        if st.button("Remove dataset"):
            st.session_state.csv_session_id = None
            st.session_state.csv_filename = ""
            st.session_state.csv_columns = []
            st.session_state.csv_dtypes = {}
            st.session_state.csv_preview = []
            st.session_state.csv_rows = 0
            st.session_state.example_questions = []
            st.session_state.stat_question = ""
            st.rerun()

    st.divider()
    st.caption("Powered by OpenAI · FastAPI · FAISS · SciPy")


# ════════════════════════════════════════════════════════════════════
# MAIN AREA — Tabs
# ════════════════════════════════════════════════════════════════════

tab_qa, tab_stats, tab_data = st.tabs([
    "💬 Ask Questions",
    "🔬 Statistical Analysis",
    "🗃️ Data Preview",
])


# ── Tab 1: Q&A over PDF ──────────────────────────────────────────
with tab_qa:
    pdf_ready = st.session_state.pdf_uploaded
    pdf_name = st.session_state.pdf_filename or "Document"
    msg_count = len(st.session_state.chat_history)

    # Hero header
    hero_doc = (
        f'<span class="qa-doc-pill">📄 {html.escape(pdf_name)}</span>'
        if pdf_ready
        else ""
    )
    st.markdown(
        f"""
        <div class="qa-hero">
            <h3>Document Q&amp;A</h3>
            <p>Ask natural-language questions about your research PDF.
            Answers are grounded in retrieved passages from the indexed document.</p>
            {hero_doc}
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Toolbar
    t_left, t_right = st.columns([3, 1], vertical_alignment="center")
    with t_left:
        if pdf_ready:
            st.markdown(
                f'<p class="qa-toolbar-meta">'
                f'{"●" if msg_count else "○"} '
                f'{msg_count} message{"s" if msg_count != 1 else ""} in this session'
                f'</p>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<p class="qa-toolbar-meta">No document indexed — upload a PDF in the sidebar</p>',
                unsafe_allow_html=True,
            )
    with t_right:
        if pdf_ready and st.session_state.chat_history:
            if st.button("Clear chat", key="clear_chat", use_container_width=True):
                st.session_state.chat_history = []
                st.session_state.qa_pending_question = None
                st.rerun()

    if not pdf_ready:
        st.markdown(
            """
            <div class="qa-empty-state">
                <h4>No document loaded yet</h4>
                <p>Upload a research PDF in the sidebar to index it for semantic search and chat.</p>
                <ol class="qa-steps">
                    <li>Open the sidebar and choose <strong>Research PDF</strong></li>
                    <li>Wait for parsing and indexing to complete</li>
                    <li>Return here to ask questions about the paper</li>
                </ol>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        with st.container(border=True):
            # Welcome + starter prompts when chat is empty
            if not st.session_state.chat_history:
                st.markdown(
                    f"""
                    <div class="qa-welcome">
                        <strong>{html.escape(pdf_name)}</strong> is ready.
                        Ask anything about methods, findings, definitions, or limitations —
                        or start with a suggested prompt below.
                    </div>
                    <p class="qa-prompt-label">Suggested questions</p>
                    """,
                    unsafe_allow_html=True,
                )
                pcols = st.columns(2, gap="small", vertical_alignment="top")
                for idx, prompt in enumerate(PDF_QA_PROMPTS):
                    with pcols[idx % 2]:
                        if st.button(
                            prompt,
                            key=f"qa_prompt_{idx}",
                            use_container_width=True,
                            type="secondary",
                        ):
                            st.session_state.qa_pending_question = prompt
                            st.rerun()

            # Process pending question (from suggested prompts)
            pending = st.session_state.qa_pending_question
            if pending:
                st.session_state.qa_pending_question = None
                with st.spinner("Searching document and generating answer…"):
                    handle_qa_question(pending)
                st.rerun()

            # Chat history
            for msg in st.session_state.chat_history:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])
                    if msg["role"] == "assistant" and msg.get("sources"):
                        render_source_cards(msg["sources"])

    question = st.chat_input(
        "Ask about methodology, findings, limitations…",
        disabled=not pdf_ready,
        key="qa_chat_input",
    )

    if question:
        with st.spinner("Searching document and generating answer…"):
            handle_qa_question(question)
        st.rerun()


# ── Tab 2: Statistical Analysis ──────────────────────────────────
with tab_stats:
    if not st.session_state.csv_session_id:
        st.markdown(
            """
            <div class="stats-hero">
                <h3>Statistical Analysis</h3>
                <p>Ask a question in plain language — the AI selects and runs the appropriate test.</p>
            </div>
            <div class="stats-empty-state">
                <h4>No dataset loaded</h4>
                <p>Upload a CSV or XLSX file in the sidebar to run hypothesis tests.</p>
                <ol>
                    <li>Open the sidebar and upload your data file</li>
                    <li>Review columns in the <strong>Data Preview</strong> tab</li>
                    <li>Ask a question here or pick a suggested example</li>
                </ol>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        fname = html.escape(st.session_state.csv_filename)
        nrows = st.session_state.csv_rows
        ncols = len(st.session_state.csv_columns)
        st.markdown(
            f"""
            <div class="stats-hero">
                <h3>Statistical Analysis</h3>
                <p>Ask a question in plain language — the AI selects the test, runs it, and explains the results.</p>
                <span class="stats-dataset-pill">📊 {fname} · {nrows:,} rows · {ncols} columns</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.container(border=True):
            if not st.session_state.example_questions:
                with st.spinner("Generating example questions for your dataset…"):
                    st.session_state.example_questions = generate_example_questions(
                        st.session_state.csv_session_id,
                        st.session_state.csv_columns,
                        st.session_state.csv_dtypes,
                    )

            st.markdown('<p class="stats-section-label">Suggested questions</p>', unsafe_allow_html=True)
            with st.expander("Browse examples for your dataset", expanded=False):
                st.markdown('<div class="stats-example-row">', unsafe_allow_html=True)
                for row_start in range(0, len(st.session_state.example_questions), 2):
                    ex_cols = st.columns(2, gap="small", vertical_alignment="top")
                    for col_idx, ex in enumerate(
                        st.session_state.example_questions[row_start : row_start + 2]
                    ):
                        with ex_cols[col_idx]:
                            if st.button(
                                ex,
                                key=f"ex_{hash(ex)}",
                                use_container_width=True,
                                type="secondary",
                            ):
                                st.session_state.stat_question = ex
                                st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)

            st.markdown('<p class="stats-section-label">Your analysis</p>', unsafe_allow_html=True)
            st.markdown(
                '<p class="stats-input-hint">Describe what you want to test — comparisons, correlations, '
                "regression, or associations. Use exact column names when possible.</p>",
                unsafe_allow_html=True,
            )
            stat_question = st.text_area(
                "Research question",
                key="stat_question",
                placeholder="e.g. Does smoking predict disease?",
                height=88,
                label_visibility="collapsed",
            )

            alpha_col, btn_col = st.columns([2, 1], gap="medium", vertical_alignment="bottom")
            with alpha_col:
                alpha = st.selectbox("Significance level (α)", [0.05, 0.01, 0.10], index=0)
            with btn_col:
                run_btn = st.button(
                    "Run Analysis",
                    type="primary",
                    disabled=not stat_question.strip(),
                    use_container_width=True,
                )

        if run_btn and stat_question.strip():
            with st.spinner("Selecting test · Running analysis · Generating explanation…"):
                result = backend(
                    "POST", "/stats/analyze",
                    json={"session_id": st.session_state.csv_session_id, "question": stat_question},
                )

            if result:
                if result.get("test_name") == "unsupported":
                    msg = html.escape(result.get("plain_explanation") or result.get("error", ""))
                    st.markdown(
                        f'<div class="stats-unsupported-box"><strong>Not supported</strong><br>{msg}</div>',
                        unsafe_allow_html=True,
                    )
                    rat = result.get("rationale")
                    if rat and rat != result.get("plain_explanation"):
                        st.caption(rat)
                elif result.get("error"):
                    err = html.escape(str(result["error"]))
                    st.markdown(
                        f'<div class="stats-error-box"><strong>Analysis could not be completed</strong><br>{err}</div>',
                        unsafe_allow_html=True,
                    )
                else:
                    render_stats_result(result)
                    st.session_state.stats_history.append({
                        "question": stat_question,
                        "result": result,
                    })

        if st.session_state.stats_history:
            st.markdown('<p class="stats-section-label">Session history</p>', unsafe_allow_html=True)
            hist_header, hist_clear = st.columns([4, 1], vertical_alignment="center")
            with hist_clear:
                if st.button("Clear history", key="clear_stats", use_container_width=True):
                    st.session_state.stats_history = []
                    st.rerun()

            for h in reversed(st.session_state.stats_history[-5:]):
                r = h["result"]
                q_short = html.escape(h["question"][:90] + ("…" if len(h["question"]) > 90 else ""))
                test_lbl = html.escape(str(r.get("test_display_name", "—")))
                p_disp = r.get("p_value")
                p_str = f"{p_disp:.4f}" if p_disp is not None else "N/A"
                with st.expander(f"{test_lbl} · p = {p_str}"):
                    st.markdown(
                        f'<p class="stats-history-item"><strong>Question:</strong> {q_short}</p>',
                        unsafe_allow_html=True,
                    )
                    if r.get("error") or r.get("test_name") == "unsupported":
                        st.markdown(r.get("plain_explanation") or r.get("error", ""))
                    elif r.get("plain_explanation"):
                        st.markdown(r["plain_explanation"])
                    else:
                        render_stats_result(r)


# ── Tab 3: Data Preview ──────────────────────────────────────────
with tab_data:
    st.markdown("### Dataset preview")
    if not st.session_state.csv_session_id:
        st.info("Upload a CSV or XLSX file to see a preview here.")
    else:
        st.markdown(
            f"**{st.session_state.csv_filename}** · "
            f"{st.session_state.csv_rows} rows · {len(st.session_state.csv_columns)} columns"
        )
        if st.session_state.csv_preview:
            st.dataframe(pd.DataFrame(st.session_state.csv_preview), use_container_width=True)

        st.markdown("**Column types:**")
        dtype_df = pd.DataFrame(
            [{"Column": col, "Type": st.session_state.csv_dtypes.get(col, "")}
             for col in st.session_state.csv_columns]
        )
        st.dataframe(dtype_df, use_container_width=True, hide_index=True)
