import asyncio
import logging
import traceback

from fastapi import APIRouter, HTTPException

from ..models.schema import StatTestRequest, StatTestResult, ExamplesRequest, ExamplesResponse
from ..services.stats_service import StatisticalAnalysisError, run_statistical_analysis, generate_valid_example_questions
from ..utils.session_store import get_session

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/analyze",
    response_model=StatTestResult,
    responses={
        404: {"description": "Session not found"},
        500: {"description": "Unexpected server error during analysis"},
    },
)
async def analyze(request: StatTestRequest):
    """
    Run a statistical analysis on the uploaded dataset.

    The LLM first inspects the question and data to select the appropriate test
    from the 4 currently active tests:
      - Independent Samples T-Test
      - Pearson Correlation
      - Simple Linear Regression
      - Chi-Square Test of Independence

    If the question cannot be answered with these tests, a polite explanation is
    returned (HTTP 200) rather than an error — so the client always gets a
    well-formed StatTestResult with test_name="unsupported".
    """
    logger.info(f"STATS: session={request.session_id}, question='{request.question[:80]}'")

    session = get_session(request.session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{request.session_id}' not found. Please upload a CSV first.",
        )

    try:
        df = session["df"]
        result = await asyncio.to_thread(run_statistical_analysis, df, request.question)
        return StatTestResult(**result)

    except Exception as e:
        logger.error(f"Stats analysis failed (500): {e}\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail=f"Analysis failed: {str(e)}",
        ) from e


@router.post(
    "/examples",
    response_model=ExamplesResponse,
    responses={
        404: {"description": "Session not found"},
    },
)
async def get_example_questions(request: ExamplesRequest):
    """
    Generate dataset-specific example questions that are guaranteed to be
    answerable with the 4 supported statistical tests.

    Each question is validated by dry-running the LLM test selector before
    being returned, so questions that would yield 'unsupported' are filtered out.
    """
    logger.info(f"EXAMPLES: session={request.session_id}, n={request.n}")

    session = get_session(request.session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{request.session_id}' not found. Please upload a CSV first.",
        )

    try:
        df = session["df"]
        questions = await asyncio.to_thread(generate_valid_example_questions, df, n=request.n)
        return ExamplesResponse(
            questions=questions,
            message=f"Generated {len(questions)} example questions.",
        )
    except Exception as e:
        logger.error(f"Example generation failed: {e}\n{traceback.format_exc()}")
        return ExamplesResponse(
            questions=[],
            message=f"Could not generate examples: {str(e)}",
        )
