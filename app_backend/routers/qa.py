import asyncio
import logging
import traceback
from fastapi import APIRouter, HTTPException

from ..models.schema import AskRequest, AnswerResponse
from ..services.qa_engine import QAEngine
from ..utils.vector_store import VectorStore

logger = logging.getLogger(__name__)
router = APIRouter()

_engine: QAEngine | None = None


def set_engine(engine: QAEngine):
    global _engine
    _engine = engine


@router.post("/ask", response_model=AnswerResponse)
async def ask_question(request: AskRequest):
    logger.info(f"ASK: '{request.question[:80]}'")
    try:
        if _engine is None:
            raise RuntimeError("QA engine not initialised")
        resp = await asyncio.to_thread(_engine.answer, request.question, top_k=request.top_k)
        return AnswerResponse(answer=resp["answer"], sources=resp["sources"])
    except Exception as e:
        logger.error(f"ASK failed: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))
