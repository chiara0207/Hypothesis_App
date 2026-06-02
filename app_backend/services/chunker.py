from typing import List, Dict
import uuid
import logging
import time

logger = logging.getLogger(__name__)


def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> List[Dict]:
    """Split text into overlapping chunks. Returns list of {id, text}."""
    chunk_start = time.time()
    if not text:
        logger.warning("Empty text provided for chunking")
        return []

    try:
        tokens = text.split()
        chunks = []
        start = 0
        n = len(tokens)

        while start < n:
            end = start
            current = []
            length = 0
            while end < n and length < chunk_size:
                token = tokens[end]
                current.append(token)
                length += len(token) + 1
                end += 1

            chunk_str = " ".join(current).strip()
            chunks.append({"id": str(uuid.uuid4()), "text": chunk_str})

            overlap_words = max(0, overlap // 5)
            next_start = end - overlap_words
            if next_start <= start:
                next_start = end
            start = next_start

        logger.info(f"Chunking done in {time.time()-chunk_start:.2f}s → {len(chunks)} chunks")
        return chunks

    except Exception as e:
        logger.error(f"Text chunking failed: {e}")
        raise
