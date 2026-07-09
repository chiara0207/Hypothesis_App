import asyncio
import logging
from typing import List

import numpy as np
import PyPDF2
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from .. import config

logger = logging.getLogger(__name__)
router = APIRouter()


class RankedPaper(BaseModel):
    filename: str
    score: float
    label: str
    explanation: str
    key_quote: str


class RankResponse(BaseModel):
    question: str
    papers: List[RankedPaper]


def _extract_text(file_bytes: bytes) -> str:
    import io
    reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
    pages = []
    for page in reader.pages[:6]:
        text = page.extract_text() or ""
        pages.append(text)
        if sum(len(p) for p in pages) > 4000:
            break
    return " ".join(pages)[:4000].strip()


def _embed(texts: List[str]) -> np.ndarray:
    from openai import OpenAI
    client = OpenAI(api_key=config.OPENAI_API_KEY)
    resp = client.embeddings.create(model=config.OPENAI_EMBEDDING_MODEL, input=texts)
    vectors = [r.embedding for r in resp.data]
    return np.array(vectors, dtype=np.float32)


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-10))


def _relevance_label(score: float) -> str:
    if score >= 0.82:
        return "Highly Relevant"
    if score >= 0.70:
        return "Relevant"
    if score >= 0.55:
        return "Somewhat Relevant"
    return "Less Relevant"


def _generate_explanations(question: str, papers: List[dict]) -> List[dict]:
    from openai import OpenAI
    client = OpenAI(api_key=config.OPENAI_API_KEY)

    paper_block = "\n\n".join(
        f"PAPER {i+1} — {p['filename']}:\n{p['text'][:800]}"
        for i, p in enumerate(papers)
    )

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a research assistant helping students evaluate papers for their thesis. "
                    "For each paper, provide:\n"
                    "1. A 2-sentence explanation of how well it fits the research question (be specific and honest)\n"
                    "2. The single most relevant quote or finding from the paper (max 30 words)\n\n"
                    "Format your response strictly as:\n"
                    "PAPER 1\nEXPLANATION: <text>\nQUOTE: <text>\n\n"
                    "PAPER 2\nEXPLANATION: <text>\nQUOTE: <text>\n\n"
                    "...and so on. Use the exact PAPER N numbering."
                ),
            },
            {
                "role": "user",
                "content": f"Research question: {question}\n\n{paper_block}",
            },
        ],
        temperature=0.2,
        max_tokens=150 * len(papers),
    )

    raw = resp.choices[0].message.content.strip()
    results = []
    for i, p in enumerate(papers):
        explanation = "Could not generate explanation."
        key_quote = "—"
        marker = f"PAPER {i+1}"
        if marker in raw:
            section = raw.split(marker)[1].split(f"PAPER {i+2}")[0] if f"PAPER {i+2}" in raw else raw.split(marker)[1]
            for line in section.splitlines():
                line = line.strip()
                if line.startswith("EXPLANATION:"):
                    explanation = line.replace("EXPLANATION:", "").strip()
                elif line.startswith("QUOTE:"):
                    key_quote = line.replace("QUOTE:", "").strip()
        results.append({"explanation": explanation, "key_quote": key_quote})
    return results


@router.post("/papers", response_model=RankResponse)
async def rank_papers(
    question: str = Form(...),
    files: List[UploadFile] = File(...),
):
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded.")
    if len(files) > 20:
        raise HTTPException(status_code=400, detail="Maximum 20 papers at a time.")

    logger.info("Ranking %d papers for question: %r", len(files), question[:80])

    papers = []
    for f in files:
        content = await f.read()
        try:
            text = _extract_text(content)
        except Exception as e:
            logger.warning("Could not extract text from %s: %s", f.filename, e)
            text = ""
        papers.append({"filename": f.filename, "text": text})

    texts_to_embed = [question] + [p["text"] if p["text"] else p["filename"] for p in papers]
    vectors = await asyncio.to_thread(_embed, texts_to_embed)
    question_vec = vectors[0]
    paper_vecs = vectors[1:]

    for i, p in enumerate(papers):
        p["score"] = _cosine_similarity(question_vec, paper_vecs[i])

    papers_with_text = [p for p in papers if p["text"]]
    papers_without_text = [p for p in papers if not p["text"]]

    explanations = (
        await asyncio.to_thread(_generate_explanations, question, papers_with_text)
        if papers_with_text
        else []
    )

    for i, p in enumerate(papers_with_text):
        p["explanation"] = explanations[i]["explanation"]
        p["key_quote"] = explanations[i]["key_quote"]

    for p in papers_without_text:
        p["explanation"] = "Could not extract text from this PDF."
        p["key_quote"] = "—"

    all_papers = sorted(papers_with_text + papers_without_text, key=lambda x: x["score"], reverse=True)

    return RankResponse(
        question=question,
        papers=[
            RankedPaper(
                filename=p["filename"],
                score=round(p["score"], 4),
                label=_relevance_label(p["score"]),
                explanation=p["explanation"],
                key_quote=p["key_quote"],
            )
            for p in all_papers
        ],
    )
