from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

# ── Upload responses ──────────────────────────────────────────────

class PDFUploadResponse(BaseModel):
    success: bool
    chunks_created: int = 0
    filename: str = ""
    message: str = ""

class CSVUploadResponse(BaseModel):
    success: bool
    session_id: str = ""
    filename: str = ""
    rows: int = 0
    columns: List[str] = []
    dtypes: Dict[str, str] = {}
    preview: List[Dict[str, Any]] = []
    message: str = ""

# ── RAG / Ask ─────────────────────────────────────────────────────

class AskRequest(BaseModel):
    question: str = Field(..., example="What methodology was used in the study?")
    top_k: int = Field(5, ge=1, le=50)

class SourceDocument(BaseModel):
    id: str
    text: str
    score: float

class AnswerResponse(BaseModel):
    answer: str
    sources: List[SourceDocument] = []

# ── Statistical analysis ──────────────────────────────────────────

class StatTestRequest(BaseModel):
    session_id: str = Field(..., description="Session ID returned from CSV upload")
    question: str = Field(..., example="Is there a significant difference in GDP between regions?")

class ExamplesRequest(BaseModel):
    session_id: str = Field(..., description="Session ID returned from CSV upload")
    n: int = Field(6, ge=1, le=12, description="Number of example questions to generate")

class ExamplesResponse(BaseModel):
    questions: List[str] = []
    message: str = ""

class AssumptionCheck(BaseModel):
    name: str
    passed: bool
    detail: str

class StatTestResult(BaseModel):
    test_name: str
    test_display_name: str
    variables_used: Dict[str, str]
    rationale: str
    statistic: Optional[float] = None
    p_value: Optional[float] = None
    additional_stats: Dict[str, Any] = {}
    assumption_checks: List[AssumptionCheck] = []
    interpretation: str
    plain_explanation: str
    significant: Optional[bool] = None
    alpha: float = 0.05
    error: Optional[str] = None

# ── Visualization ─────────────────────────────────────────────────

class VisualizationRequest(BaseModel):
    session_id: str = Field(..., description="Session ID returned from CSV upload; used to fetch the analyzed dataset")
    test_name: str = Field(..., example="independent_ttest")
    variables_used: Dict[str, str] = Field(default_factory=dict, description="Column roles from the StatTestResult, e.g. {'group': 'method', 'y': 'score'}")
    p_value: Optional[float] = Field(None, description="p-value from the statistical test")
    alpha: float = Field(0.05, description="Significance threshold used for the test")

class VisualizationChart(BaseModel):
    key: str
    title: str
    figure: Dict[str, Any]
    interpretation: str

class VisualizationSuiteResponse(BaseModel):
    charts: List[VisualizationChart] = []
