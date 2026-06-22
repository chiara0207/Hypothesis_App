import logging
from typing import List

from fastapi import APIRouter
from pydantic import BaseModel

from .. import config

logger = logging.getLogger(__name__)
router = APIRouter()


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: List[ChatMessage] = []


class ChatResponse(BaseModel):
    reply: str


SYSTEM_PROMPT = """You are a curious, witty, and knowledgeable hypothesis analyst.
Your job is to engage with ANY hypothesis the user throws at you — from rigorous scientific questions
to completely wild, absurd, or whimsical ideas.

For serious hypotheses: discuss the evidence, plausibility, relevant science, and what research suggests.
For fun or outlandish ones (e.g. "Will there be unicorns one day?"): engage playfully but intelligently —
explore the idea creatively, discuss what it would actually take, reference real science where relevant
(genetics, evolution, history, etc.), and have fun with it without dismissing it.

Always:
- Be conversational and engaging, not dry or lecture-like
- Ask a follow-up question to keep the conversation going
- Be honest when something is purely speculative
- Never refuse a hypothesis — treat every idea as worth exploring
- Keep responses concise (3-5 sentences + a follow-up question)"""


@router.post("/message", response_model=ChatResponse)
def chat(req: ChatRequest):
    from openai import OpenAI
    client = OpenAI(api_key=config.OPENAI_API_KEY)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in req.history[-10:]:
        messages.append({"role": msg.role, "content": msg.content})
    messages.append({"role": "user", "content": req.message})

    logger.info("Chat message: %r", req.message[:80])
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0.7,
        max_tokens=400,
    )
    return ChatResponse(reply=resp.choices[0].message.content.strip())
