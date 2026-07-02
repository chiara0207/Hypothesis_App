import logging
import traceback

from fastapi import APIRouter, HTTPException

from .. import config
from ..models.schema import (
    VisualizationChatRequest,
    VisualizationChatResponse,
    VisualizationRequest,
    VisualizationSuiteResponse,
)
from ..services.visualization_service import build_visualization_suite, describe_chart_context
from ..utils.session_store import get_session

logger = logging.getLogger(__name__)
router = APIRouter()

CHART_QA_SYSTEM_PROMPT = """You are a friendly statistics tutor helping someone understand a specific \
chart from their own data analysis. You will be given the chart's general explanation plus the concrete \
numbers computed from their data — ground your answer in those numbers, never invent numbers of your own. \
Explain concepts in plain, jargon-light language a beginner can follow. Keep answers concise (3-6 sentences) \
unless the user explicitly asks for more depth. If asked something unrelated to the chart or the data, \
gently steer back to what the chart shows."""


@router.post(
    "/suite",
    response_model=VisualizationSuiteResponse,
    responses={
        404: {"description": "Session not found"},
        500: {"description": "Unexpected server error while building charts"},
    },
)
async def suite(request: VisualizationRequest):
    """
    Build the full set of Plotly charts (plus plain-language captions) for a
    completed statistical test result. Chart selection depends on the test:
      - t-test / ANOVA: boxplot, violin plot, bell curves, grouped histogram
      - correlation / regression: scatterplot, histograms, correlation matrix
      - chi-square: contingency heatmap
    Every suite also includes the p-value-vs-alpha significance gauge.
    """
    logger.info(
        f"VISUALIZATION: session={request.session_id}, test={request.test_name}, "
        f"p_value={request.p_value}, alpha={request.alpha}"
    )

    session = get_session(request.session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{request.session_id}' not found. Please upload a CSV first.",
        )

    try:
        df = session["df"]
        charts = build_visualization_suite(
            df, request.test_name, request.variables_used, request.p_value, request.alpha
        )
        return VisualizationSuiteResponse(charts=charts)
    except Exception as e:
        logger.error(f"Visualization suite failed (500): {e}\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail=f"Visualization failed: {str(e)}",
        ) from e


@router.post(
    "/ask",
    response_model=VisualizationChatResponse,
    responses={
        404: {"description": "Session not found"},
        500: {"description": "Unexpected server error while answering"},
    },
)
async def ask(request: VisualizationChatRequest):
    """
    Answer a follow-up question about a specific chart, grounded in that
    chart's general explanation plus the concrete numbers from the user's data.
    """
    logger.info(f"VIZ ASK: session={request.session_id}, chart={request.chart_key}, question={request.question[:80]!r}")

    session = get_session(request.session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{request.session_id}' not found. Please upload a CSV first.",
        )

    try:
        df = session["df"]
        context = describe_chart_context(
            df, request.test_name, request.variables_used, request.chart_key, request.p_value, request.alpha
        )

        from openai import OpenAI
        client = OpenAI(api_key=config.OPENAI_API_KEY)

        messages = [
            {"role": "system", "content": CHART_QA_SYSTEM_PROMPT},
            {"role": "system", "content": f"Chart context:\n{context}"},
        ]
        for msg in request.history[-8:]:
            messages.append({"role": msg.role, "content": msg.content})
        messages.append({"role": "user", "content": request.question})

        resp = client.chat.completions.create(
            model=config.OPENAI_CHAT_MODEL,
            messages=messages,
            temperature=0.4,
            max_tokens=400,
        )
        return VisualizationChatResponse(answer=resp.choices[0].message.content.strip())
    except Exception as e:
        logger.error(f"Visualization chart Q&A failed (500): {e}\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail=f"Could not answer question: {str(e)}",
        ) from e
