from io import BytesIO
from typing import List
import logging
import time
import re

logger = logging.getLogger(__name__)

try:
    from PyPDF2 import PdfReader
except Exception:
    PdfReader = None


def clean_extracted_text(text: str) -> str:
    """
    Normalize PDF-extracted text while preserving word boundaries.

    PyPDF2 (and similar extractors) often insert hard line breaks and soft
    hyphens; they should not be confused with spaces between words.
    """
    if not text:
        return ""

    # Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Remove soft hyphens (U+00AD) sometimes present in PDFs
    text = text.replace("\u00ad", "")

    # De-hyphenate words broken across lines: "autono-\nmy" -> "autonomy"
    text = re.sub(r"(\w)-\n\s*(\w)", r"\1\2", text)

    # Line break in the middle of a sentence (not a paragraph break)
    text = re.sub(r"([a-z0-9,;])\n([a-z])", r"\1 \2", text)

    # Collapse horizontal whitespace (keep newlines for paragraph structure)
    text = re.sub(r"[ \t]+", " ", text)

    # Trim spaces around newlines
    text = re.sub(r" *\n *", "\n", text)

    # Collapse excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def parse_pdf(file_bytes: bytes) -> str:
    parse_start = time.time()
    logger.debug(f"parse_pdf started, file size: {len(file_bytes)} bytes")

    if PdfReader is None:
        logger.warning("PyPDF2 not available, using fallback byte decoding")
        return file_bytes.decode("utf-8", errors="ignore")

    try:
        stream = BytesIO(file_bytes)
        reader = PdfReader(stream)
        logger.info(f"PDF reader created, pages: {len(reader.pages)}")

        texts: List[str] = []
        for idx, page in enumerate(reader.pages):
            try:
                page_text = page.extract_text() or ""
                texts.append(page_text)
                logger.debug(f"Page {idx}: {len(page_text)} chars")
            except Exception as e:
                logger.warning(f"Failed to extract page {idx}: {e}")
                continue

        result = "\n".join(texts)
        result = clean_extracted_text(result)
        logger.info(f"PDF parsed in {time.time()-parse_start:.2f}s, {len(result)} chars")
        return result

    except Exception as e:
        logger.error(f"PDF parsing failed: {e}")
        return ""
