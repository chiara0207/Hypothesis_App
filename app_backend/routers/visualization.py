import logging
import traceback

from fastapi import APIRouter, HTTPException

from ..models.schema import VisualizationRequest, VisualizationSuiteResponse
from ..services.visualization_service import build_visualization_suite
from ..utils.session_store import get_session

logger = logging.getLogger(__name__)
router = APIRouter()


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
