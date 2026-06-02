import logging
import traceback
from io import BytesIO

import pandas as pd
from fastapi import APIRouter, File, HTTPException, UploadFile

from ..models.schema import PDFUploadResponse, CSVUploadResponse
from ..services import chunker, embedder, parser
from ..utils.session_store import create_session
from ..utils.vector_store import VectorStore

logger = logging.getLogger(__name__)
router = APIRouter()

# Shared vector store (imported/set from main)
_vector_store: VectorStore | None = None


def set_vector_store(store: VectorStore):
    global _vector_store
    _vector_store = store


# ── PDF Upload ────────────────────────────────────────────────────

@router.post("/pdf", response_model=PDFUploadResponse)
async def upload_pdf(file: UploadFile = File(...)):
    logger.info(f"PDF upload: {file.filename}")
    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Empty file")

        text = parser.parse_pdf(content)
        if not text.strip():
            return PDFUploadResponse(
                success=False, chunks_created=0,
                filename=file.filename or "",
                message="No readable text found in PDF."
            )

        chunks = chunker.chunk_text(text)
        if not chunks:
            return PDFUploadResponse(success=False, chunks_created=0, filename=file.filename or "")

        texts = [c["text"] for c in chunks]
        ids = [c["id"] for c in chunks]
        metadatas = [{"text": t, "source": file.filename} for t in texts]

        vectors = embedder.embed_texts(texts)

        if _vector_store is None:
            raise RuntimeError("Vector store not initialised")

        _vector_store.add(ids, vectors, metadatas)

        logger.info(f"PDF ingested: {len(chunks)} chunks")
        return PDFUploadResponse(
            success=True,
            chunks_created=len(chunks),
            filename=file.filename or "",
            message=f"Successfully ingested {len(chunks)} chunks from '{file.filename}'.",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"PDF upload failed: {e}\n{traceback.format_exc()}")
        return PDFUploadResponse(success=False, chunks_created=0, filename=file.filename or "", message=str(e))


# ── CSV/XLSX Upload ───────────────────────────────────────────────

@router.post("/csv", response_model=CSVUploadResponse)
async def upload_csv(file: UploadFile = File(...)):
    logger.info(f"CSV upload: {file.filename}")
    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Empty file")

        fname = (file.filename or "").lower()
        if fname.endswith(".xlsx") or fname.endswith(".xls"):
            df = pd.read_excel(BytesIO(content))
        elif fname.endswith(".csv"):
            df = pd.read_csv(BytesIO(content))
        else:
            # Try CSV as fallback
            try:
                df = pd.read_csv(BytesIO(content))
            except Exception:
                raise HTTPException(status_code=400, detail="Unsupported file type. Upload CSV or XLSX.")

        if df.empty:
            return CSVUploadResponse(success=False, message="Uploaded file contains no data.")

        session_id = create_session(df, file.filename or "")

        preview = df.head(5).fillna("").astype(str).to_dict(orient="records")
        dtypes = {col: str(dtype) for col, dtype in df.dtypes.items()}

        return CSVUploadResponse(
            success=True,
            session_id=session_id,
            filename=file.filename or "",
            rows=len(df),
            columns=list(df.columns),
            dtypes=dtypes,
            preview=preview,
            message=f"Dataset loaded: {len(df)} rows × {len(df.columns)} columns.",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"CSV upload failed: {e}\n{traceback.format_exc()}")
        return CSVUploadResponse(success=False, message=str(e))
