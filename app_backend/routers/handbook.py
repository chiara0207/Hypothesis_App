import logging
import traceback

from fastapi import APIRouter, HTTPException

from .. import config
from ..models.schema import (
    HandbookChatRequest,
    HandbookChatResponse,
    HandbookResponse,
)
from ..services.handbook_service import describe_test_selection_context, list_concepts

logger = logging.getLogger(__name__)
router = APIRouter()

HANDBOOK_SYSTEM_PROMPT = """You are a friendly statistics tutor helping someone build intuition for \
hypothesis testing. Explain concepts in plain, jargon-light language a beginner can follow, using \
concrete examples. If the user's message includes a specific test result (statistic, p-value, \
rationale, assumption checks), ground your answer in those numbers and explain *this* result — never \
invent numbers of your own. Keep answers concise (3-6 sentences) unless the user explicitly asks for \
more depth. If asked something entirely unrelated to statistics, gently steer back to the topic."""


@router.get("/concepts", response_model=HandbookResponse)
async def concepts():
    """Full glossary: core statistics concepts plus every supported hypothesis test."""
    return HandbookResponse(concepts=list_concepts())


@router.post(
    "/ask",
    response_model=HandbookChatResponse,
    responses={500: {"description": "Unexpected server error while answering"}},
)
async def ask(request: HandbookChatRequest):
    """
    Answer a free-form statistics question. If test_name and its result fields
    are supplied, ground the answer in that specific, already-computed result
    (e.g. 'why was a t-test chosen and what does my p-value mean') in addition
    to general concept explanations.
    """
    logger.info(f"HANDBOOK ASK: test={request.test_name}, question={request.question[:80]!r}")

    try:
        context = describe_test_selection_context(
            request.test_name,
            request.variables_used,
            request.rationale,
            request.statistic,
            request.p_value,
            request.alpha,
            request.significant,
            [c.model_dump() for c in request.assumption_checks],
        )

        from openai import OpenAI
        client = OpenAI(api_key=config.OPENAI_API_KEY)

        messages = [{"role": "system", "content": HANDBOOK_SYSTEM_PROMPT}]
        if context:
            messages.append({"role": "system", "content": f"Current test result context:\n{context}"})
        for msg in request.history[-8:]:
            messages.append({"role": msg.role, "content": msg.content})
        messages.append({"role": "user", "content": request.question})

        resp = client.chat.completions.create(
            model=config.OPENAI_CHAT_MODEL,
            messages=messages,
            temperature=0.4,
            max_tokens=400,
        )
        return HandbookChatResponse(answer=resp.choices[0].message.content.strip())
    except Exception as e:
        logger.error(f"Handbook Q&A failed (500): {e}\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail=f"Could not answer question: {str(e)}",
        ) from e
