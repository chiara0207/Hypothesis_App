from typing import Dict, Any
import logging
import time

from openai import OpenAI
from ..utils.vector_store import VectorStore
from ..services.embedder import embed_texts
from ..config import (
    OPENAI_API_KEY,
    OPENAI_CHAT_MODEL,
    OPENAI_MAX_CONTEXT_CHARS,
    OPENAI_MAX_OUTPUT_TOKENS,
)

logger = logging.getLogger(__name__)

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        if not OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not set")
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client


class QAEngine:
    def __init__(self, store: VectorStore, gen_model: str = OPENAI_CHAT_MODEL):
        self.store = store
        self.gen_model = gen_model

    def answer(self, question: str, top_k: int = 5) -> Dict[str, Any]:
        start = time.time()
        logger.info(f"QAEngine.answer: '{question[:80]}'")

        q_emb = embed_texts([question])[0]
        hits = self.store.query(q_emb, top_k=top_k)

        context_parts = []
        sources = []
        for idx, (doc_id, score, meta) in enumerate(hits):
            text = meta.get("text", "")
            context_parts.append(f"[Source {idx+1}, relevance={score:.2f}]\n{text}")
            sources.append({"id": doc_id, "text": text, "score": score})

        context = "\n\n".join(context_parts)
        if len(context) > OPENAI_MAX_CONTEXT_CHARS:
            context = context[:OPENAI_MAX_CONTEXT_CHARS] + "\n...[truncated]"

        client = _get_client()
        resp = client.chat.completions.create(
            model=self.gen_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a helpful research assistant that answers questions based on "
                        "the provided document context. Use the sources to give a precise, "
                        "well-structured answer. If the answer is not in the context, say so clearly. "
                        "Cite source numbers when applicable."
                    ),
                },
                {
                    "role": "user",
                    "content": f"CONTEXT:\n{context}\n\nQUESTION:\n{question}",
                },
            ],
            temperature=0,
            max_tokens=OPENAI_MAX_OUTPUT_TOKENS,
        )

        answer_text = (resp.choices[0].message.content or "").strip()
        logger.info(f"QAEngine answer generated in {time.time()-start:.2f}s")
        return {"answer": answer_text, "sources": sources}
