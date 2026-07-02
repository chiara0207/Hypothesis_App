"""
Plotly Dash frontend for the Statistical Hypothesis Testing Assistant.
Accommodates all multi-tab functionalities, automated test visualizations, 
and plain-language interpretations.
"""

import base64
import html
import io
import json
from io import BytesIO
from typing import Any, Dict, List, Optional

import dash
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
from dash import dcc, html, callback, Input, Output, State, MATCH, ALL

# ── Configuration & Backend Utilities ──────────────────────────────
BACKEND_URL = "http://localhost:8000"

app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP, dbc.icons.BOOTSTRAP],
    suppress_callback_exceptions=True
)
app.title = "Statistical Hypothesis Testing Assistant"

def backend_request(method: str, path: str, **kwargs) -> Optional[Dict]:
    """Helper to communicate with the FastAPI backend."""
    try:
        resp = requests.request(method, f"{BACKEND_URL}{path}", timeout=120, **kwargs)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"Backend communication error: {e}")
        return None

# ── Graphical Visualization Generator ──────────────────────────────
def generate_stats_visualization(p_value: Optional[float], alpha: float, test_name: str):
    """
    Generates an interactive Plotly visualization for the statistical test results,
    rendering either a significance gauge or a visual hypothesis testing distribution map.
    """
    if p_value is None:
        # Fallback empty figure
        fig = go.Figure()
        fig.update_layout(title="No visual data available for this analysis type.")
        return fig

    # Create a clean, intuitive Gauge chart mapping out the Alpha threshold vs p-value
    fig = go.Figure(go.Indicator(
        mode = "gauge+number+delta",
        value = p_value,
        delta = {'reference': alpha, 'position': "top", 'relative': False, 'valueformat': '.4f'},
        domain = {'x': [0, 1], 'y': [0, 1]},
        title = {'text': f"p-value vs Alpha ({alpha})", 'font': {'size': 16, 'color': "#1e3a5f"}},
        gauge = {
            'axis': {'range': [0, max(alpha * 2, min(1.0, p_value * 1.2, 0.2))], 'tickformat': '.3f'},
            'bar': {'color': "#1e3a5f", 'thickness': 0.25},
            'bgcolor': "white",
            'borderwidth': 1,
            'bordercolor': "#d4e2ef",
            'steps': [
                {'range': [0, alpha], 'color': '#e6f4ec'}, # Significant zone (Green)
                {'range': [alpha, 1.0], 'color': '#fdecea'} # Non-significant zone (Red)
            ],
            'threshold': {
                'line': {'color': "red", 'width': 3},
                'thickness': 0.75,
                'value': alpha
            }
        }
    ))

    # Clean layout tailoring
    fig.update_layout(
        height=260,
        margin=dict(l=30, r=30, t=40, b=20),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
    )
    return fig


# ── App Layout ─────────────────────────────────────────────────────
app.layout = dbc.Container([
    # Store components to track cross-tab session data natively in Dash
    dcc.Store(id="session-store", data={
        "pdf_uploaded": False, "pdf_filename": "",
        "csv_session_id": None, "csv_filename": "", "csv_rows": 0, "csv_cols_count": 0,
        "chat_history": [], "stats_history": [], "search_results": None, "rank_results": None
    }),
    
    # Header Banner
    dbc.Row([
        dbc.Col([
            html.Div([
                html.H1([html.I(className="bi bi-bar-chart-fill me-3"), "Statistical Hypothesis Testing Assistant"], 
                        style={"fontSize": "1.8rem", "margin": 0}),
                html.P("Upload a research PDF and/or dataset — ask questions in plain language. The assistant computes tests and visualizes results instantly.",
                        style={"margin": "0.3rem 0 0", "opacity": 0.85, "fontSize": "0.95rem"})
            ], className="p-4 rounded-3 text-white mb-4", style={"background": "linear-gradient(135deg, #1e3a5f 0%, #2d6a9f 100%)"})
        ], width=12)
    ]),

    # Main Workspace split layout
    dbc.Row([
        # Sidebar Panel
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H4([html.I(className="bi bi-folder-fill me-2"), "Upload Files"], className="card-title text-light mb-3"),
                    
                    # Section: PDF
                    html.Label("📄 Research PDF (Optional)", className="text-muted small fw-bold text-uppercase"),
                    dcc.Upload(
                        id="upload-pdf",
                        children=html.Div(["Drag & Drop or ", html.A("Select PDF")]),
                        className="p-3 text-center border rounded mb-3 text-white-50 style-upload-box",
                        multiple=False
                    ),
                    html.Div(id="pdf-status-area", className="mb-3 small"),
                    
                    html.Hr(className="text-white-50"),
                    
                    # Section: Dataset
                    html.Label("📊 Dataset (CSV / XLSX)", className="text-muted small fw-bold text-uppercase"),
                    dcc.Upload(
                        id="upload-dataset",
                        children=html.Div(["Drag & Drop or ", html.A("Select Data")]),
                        className="p-3 text-center border rounded mb-3 text-white-50 style-upload-box",
                        multiple=False
                    ),
                    html.Div(id="dataset-status-area", className="small"),
                ])
            ], color="#1a2b42", className="text-white h-100 p-2")
        ], lg=3, md=4, className="mb-4"),

        # Tab Window Contents
        dbc.Col([
            dbc.Tabs([
                dbc.Tab(label="💬 Ask Questions", tab_id="tab-qa", className="p-3 border-start border-end border-bottom bg-white rounded-bottom"),
                dbc.Tab(label="🔬 Statistical Analysis", tab_id="tab-stats", className="p-3 border-start border-end border-bottom bg-white rounded-bottom"),
                dbc.Tab(label="🗃️ Data Preview", tab_id="tab-preview", className="p-3 border-start border-end border-bottom bg-white rounded-bottom"),
                dbc.Tab(label="🔍 Find Papers", tab_id="tab-search", className="p-3 border-start border-end border-bottom bg-white rounded-bottom"),
                dbc.Tab(label="🤖 Hypothesis Chat", tab_id="tab-chat", className="p-3 border-start border-end border-bottom bg-white rounded-bottom"),
                dbc.Tab(label="📑 Rank Papers", tab_id="tab-rank", className="p-3 border-start border-end border-bottom bg-white rounded-bottom"),
            ], id="main-tabs", active_tab="tab-qa")
        ], lg=9, md=8)
    ])
], fluid=True, className="py-4 px-lg-5", style={"backgroundColor": "#f8fafc", "minHeight": "100vh"})


# ── Tab Content Renderer Callback ─────────────────────────────────
@callback(
    Output("main-tabs", "children"),
    Input("main-tabs", "active_tab"),
    Input("session-store", "data")
)
def render_tab_content(active_tab, session_data):
    """Dynamically re-renders contents corresponding to the active view state."""
    
    # TAB 1: PDF Q&A View
    if active_tab == "tab-qa":
        if not session_data["pdf_uploaded"]:
            return html.Div([
                html.H4("No document loaded yet", className="text-dark font-weight-bold"),
                html.P("Upload a research PDF in the sidebar to index it for semantic query operations.")
            ], className="p-5 text-center bg-light border rounded-3 m-3")
        
        chat_blocks = []
        for msg in session_data["chat_history"]:
            align = "text-end bg-light" if msg["role"] == "user" else "text-start border"
            chat_blocks.append(html.Div([
                html.Strong(f"{msg['role'].capitalize()}: "),
                dcc.Markdown(msg["content"], className="d-inline-block p-2 rounded")
            ], className=f"p-2 my-2 rounded {align}"))
            
        return html.Div([
            html.Div(chat_blocks, style={"height": "350px", "overflowY": "auto"}, className="p-3 bg-white border rounded mb-3"),
            dbc.InputGroup([
                dbc.Input(id="qa-input-box", placeholder="Ask a question about the study methodology or framework..."),
                dbc.Button("Submit", id="qa-submit-btn", color="primary")
            ])
        ])

    # TAB 2: Statistical Analysis Workspace
    elif active_tab == "tab-stats":
        if not session_data["csv_session_id"]:
            return html.Div([
                html.H4("No dataset loaded yet", className="text-dark font-weight-bold"),
                html.P("Upload a dataset file (CSV/XLSX) in the sidebar to unlock automated inference testing.")
            ], className="p-5 text-center bg-light border rounded-3 m-3")
        
        return html.Div([
            html.Label("State your evaluation or research query using data variables:", className="fw-bold mb-2"),
            dbc.Textarea(id="stat-query-text", placeholder="e.g., Does column_A have a significant linear correlation with column_B?", className="mb-3"),
            
            dbc.Row([
                dbc.Col([
                    html.Label("Significance Level (α):", className="small fw-bold text-muted"),
                    dcc.Dropdown(options=[0.01, 0.05, 0.10], value=0.05, id="stats-alpha-select", clearable=False)
                ], width=4),
                dbc.Col([
                    dbc.Button("Run Inference Engine", id="run-stats-btn", color="success", className="w-100", style={"marginTop": "24px"})
                ], width=4)
            ], className="mb-4"),
            
            # Dynamic Results Block containing the graphical and simple text output
            html.Div(id="stats-output-container")
        ])

    # TAB 3: Data Preview
    elif active_tab == "tab-preview":
        if not session_data["csv_session_id"]:
            return html.Div("Upload a source data file to inspect features.", className="text-muted p-4")
        return html.Div([
            html.H5(f"Dataset: {session_data['csv_filename']} Preview"),
            html.P(f"Dimensions: {session_data['csv_rows']} rows x {session_data['csv_cols_count']} columns", className="text-muted small"),
            html.Div(id="preview-datatable-container")
        ], className="p-3")

    # TAB 4: Find Papers
    elif active_tab == "tab-search":
        return html.Div([
            html.Label("Enter a hypothesis or topic to crawl Semantic Scholar & arXiv:", className="fw-bold mb-2"),
            dbc.InputGroup([
                dbc.Input(id="search-query-input", placeholder="e.g., Impact of sleep tracking on behavioral metrics"),
                dbc.Button("Search Literature", id="search-papers-btn", color="primary")
            ], className="mb-3"),
            html.Div(id="search-results-container")
        ])

    # TAB 5: General Hypothesis Chatbot
    elif active_tab == "tab-chat":
        return html.Div([
            html.Div("Welcome to the speculative hypothesis lounge. Propose any theoretical logic below.", className="alert alert-info"),
            html.Div(id="hypo-chat-box", style={"height": "300px", "overflowY": "auto"}, className="p-3 mb-2 bg-light border rounded"),
            dbc.InputGroup([
                dbc.Input(id="hypo-chat-input", placeholder="Propose an alternative physics or social rule framework..."),
                dbc.Button("Send", id="hypo-chat-submit", color="dark")
            ])
        ])

    # TAB 6: Document Ranking Suite
    elif active_tab == "tab-rank":
        return html.Div([
            html.Label("Topic/Thesis Definition:", className="fw-bold mb-2"),
            dbc.Input(id="rank-thesis-input", placeholder="Paste the central argument or question to score incoming papers against...", className="mb-3"),
            html.Label("Upload target PDFs to evaluate (Batch):", className="small fw-bold text-muted"),
            dcc.Upload(id="rank-uploader-box", children=html.Div(["Upload PDFs"]), className="p-4 border rounded text-center bg-light mb-3", multiple=True),
            dbc.Button("Run Matrix Evaluation", id="execute-ranking-btn", color="warning", className="mb-3"),
            html.Div(id="ranking-results-layout")
        ])

    return html.Div("Select a system workspace module.")


# ── Inference Engine & Graph Callback ──────────────────────────────
@callback(
    Output("stats-output-container", "children"),
    Input("run-stats-btn", "n_clicks"),
    State("stat-query-text", "value"),
    State("stats-alpha-select", "value"),
    State("session-store", "data"),
    prevent_initial_call=True
)
def handle_statistical_execution(n_clicks, query, alpha, session_data):
    if not query or not n_clicks:
        return dash.no_update
        
    payload = {"session_id": session_data["csv_session_id"], "question": query}
    result = backend_request("POST", "/stats/analyze", json=payload)
    
    if not result:
        return dbc.Alert("Error interfacing with data analytical microservice.", color="danger")
        
    if result.get("test_name") == "unsupported" or result.get("error"):
        return dbc.Alert(f"Execution Terminated: {result.get('plain_explanation', result.get('error'))}", color="warning")

    p_val = result.get("p_value")
    sig_status = result.get("significant")
    
    # Resolve design elements based on statistical outcomes
    alert_color = "success" if sig_status else "secondary"
    alert_text = "Statistically Significant Result Detected" if sig_status else "No Statistically Significant Patterns Found"
    
    # Injecting the requested dynamic Plotly Gauge chart
    graphical_viz = dcc.Graph(figure=generate_stats_visualization(p_val, alpha, result.get("test_display_name", "")))

    return html.Div([
        dbc.Alert([html.H5(alert_text, className="alert-heading m-0")], color=alert_color, className="mb-3"),
        
        dbc.Row([
            # Left: Metrics and Technical Breakdown
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader(result.get("test_display_name", "Test Diagnostics"), className="fw-bold"),
                    dbc.CardBody([
                        html.P([html.Strong("p-value: "), f"{p_val:.5f}" if p_val is not None else "N/A"]),
                        html.P([html.Strong("Test Statistic: "), f"{result.get('statistic', 0):.4f}"]),
                        html.P([html.Strong("Rationale: "), result.get("rationale", "—")]),
                    ])
                ], className="mb-3")
            ], lg=6),
            
            # Right: Requested Graph Visualization Window
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader("Significance Map Chart", className="fw-bold"),
                    dbc.CardBody([graphical_viz], className="p-0")
                ], className="mb-3")
            ], lg=6)
        ]),
        
        # Bottom: Requested Clear Simple Language Interpretations Layout
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader("Plain Language Translation", className="bg-info text-white fw-bold"),
                    dbc.CardBody(dcc.Markdown(result.get("plain_explanation", "No translation generated.")), className="bg-light")
                ], className="mb-3")
            ], md=6),
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader("Technical Domain Conclusion", className="bg-dark text-white fw-bold"),
                    dbc.CardBody(dcc.Markdown(result.get("interpretation", "No interpretation generated.")), className="bg-light")
                ], className="mb-3")
            ], md=6)
        ])
    ])


# ── CSS Configurations Injection ──────────────────────────────────
app.index_string = '''
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <style>
            .style-upload-box {
                border-style: dashed !important;
                border-color: rgba(255, 255, 255, 0.25) !important;
                background-color: rgba(255, 255, 255, 0.05);
                cursor: pointer;
                transition: background-color 0.2s ease;
            }
            .style-upload-box:hover {
                background-color: rgba(255, 255, 255, 0.1);
            }
        </style>
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>
'''

# ── CSV / XLSX Dataset Upload Processing Callback ──────────────────
@callback(
    [Output("session-store", "data"),
     Output("dataset-status-area", "children"),
     Output("dataset-status-area", "className")],
    [Input("upload-dataset", "contents")],
    [State("upload-dataset", "filename"),
     State("session-store", "data")],
    prevent_initial_call=True
)
def process_dataset_upload(contents, filename, session_data):
    if not contents:
        return dash.no_update, dash.no_update, dash.no_update

    try:
        # 1. Decode the base64 string sent by the dcc.Upload dropzone
        content_type, content_string = contents.split(',')
        decoded = base64.b64decode(content_string)
        
        # 2. Package it exactly how your FastAPI /upload/csv endpoint expects it
        files = {"file": (filename, decoded, "text/csv" if filename.endswith('.csv') else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
        
        # 3. Ship it off to your real backend running on port 8000
        result = backend_request("POST", "/upload/csv", files=files)
        
        if result and result.get("success"):
            # Update your cross-tab session data store with the incoming metadata
            session_data["csv_session_id"] = result["session_id"]
            session_data["csv_filename"] = filename
            session_data["csv_rows"] = result["rows"]
            session_data["csv_cols_count"] = len(result["columns"])
            
            status_message = html.Div([
                html.Span(f"✅ {filename}", className="fw-bold d-block text-success"),
                html.Caption(f"{result['rows']} rows · {len(result['columns'])} columns", className="text-white-50 d-block")
            ])
            return session_data, status_message, "text-success mt-2"
        else:
            error_msg = result.get("message", "Upload failed on server side.") if result else "Backend completely unreachable."
            return session_data, html.Span(f"❌ {error_msg}", className="text-danger"), "text-danger mt-2"
            
    except Exception as e:
        return session_data, html.Span(f"❌ Processing Error: {str(e)}", className="text-danger"), "text-danger mt-2"

if __name__ == "__main__":
    app.run(debug=True, port=8050)