import logging
from typing import List, Optional

import requests
from fastapi import APIRouter
from pydantic import BaseModel

from .. import config

logger = logging.getLogger(__name__)
router = APIRouter()

SEMANTIC_SCHOLAR_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
SEMANTIC_SCHOLAR_FIELDS = "title,authors,abstract,year,citationCount,externalIds,openAccessPdf,url"


class SearchRequest(BaseModel):
    question: str
    limit: int = 10


class PaperResult(BaseModel):
    title: str
    authors: List[str]
    abstract: Optional[str]
    year: Optional[int]
    citation_count: Optional[int]
    doi: Optional[str]
    pdf_url: Optional[str]
    paper_url: Optional[str]


class SearchResponse(BaseModel):
    query_used: str
    results: List[PaperResult]
    total_found: int


def _extract_keywords(question: str) -> str:
    """Use OpenAI to distill a hypothesis into a focused search query."""
    from openai import OpenAI
    client = OpenAI(api_key=config.OPENAI_API_KEY)
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a research librarian. Convert the user's hypothesis or research question "
                    "into a concise academic search query (max 8 words, no boolean operators). "
                    "Return only the query string, nothing else."
                ),
            },
            {"role": "user", "content": question},
        ],
        temperature=0,
        max_tokens=40,
    )
    return resp.choices[0].message.content.strip().strip('"')


def _search_semantic_scholar(query: str, limit: int) -> dict:
    params = {
        "query": query,
        "limit": min(limit, 20),
        "fields": SEMANTIC_SCHOLAR_FIELDS,
    }
    headers = {"User-Agent": "HypothesisApp/1.0"}
    resp = requests.get(SEMANTIC_SCHOLAR_URL, params=params, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json()


@router.post("/papers", response_model=SearchResponse)
def search_papers(req: SearchRequest):
    query = _extract_keywords(req.question)
    logger.info("Paper search: question=%r → query=%r", req.question, query)

    data = _search_semantic_scholar(query, req.limit)
    papers = data.get("data", [])
    total = data.get("total", len(papers))

    results = []
    for p in papers:
        ext_ids = p.get("externalIds") or {}
        pdf_info = p.get("openAccessPdf") or {}
        results.append(
            PaperResult(
                title=p.get("title", "Untitled"),
                authors=[a["name"] for a in (p.get("authors") or [])],
                abstract=p.get("abstract"),
                year=p.get("year"),
                citation_count=p.get("citationCount"),
                doi=ext_ids.get("DOI"),
                pdf_url=pdf_info.get("url"),
                paper_url=p.get("url"),
            )
        )

    return SearchResponse(query_used=query, results=results, total_found=total)
