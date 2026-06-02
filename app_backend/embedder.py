from typing import List
import logging
import time

from openai import OpenAI
from ..config import OPENAI_API_KEY, OPENAI_EMBEDDING_MODEL

logger = logging.getLogger(__name__)

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        if not OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not set")
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client


def embed_texts(texts: List[str], model_name: str | None = None) -> List[List[float]]:
    """Return embeddings for a list of texts using OpenAI."""
    embed_start = time.time()
    model = model_name or OPENAI_EMBEDDING_MODEL

    if not texts:
        return []

    try:
        client = _get_client()
        resp = client.embeddings.create(model=model, input=texts)
        result = [d.embedding for d in resp.data]
        logger.info(f"Embedded {len(result)} texts in {time.time()-embed_start:.2f}s (dim={len(result[0]) if result else 0})")
        return result
    except Exception as e:
        logger.error(f"Embedding failed: {e}", exc_info=True)
        raise
