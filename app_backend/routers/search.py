import logging
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional

import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import config

logger = logging.getLogger(__name__)
router = APIRouter()

SEMANTIC_SCHOLAR_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
SEMANTIC_SCHOLAR_FIELDS = "title,authors,abstract,year,citationCount,externalIds,openAccessPdf,url"


class SearchRequest(BaseModel):
    question: str
    limit: int = 10
    sources: List[str] = ["Semantic Scholar", "arXiv", "PubMed", "OpenAlex"]


class PaperResult(BaseModel):
    title: str
    authors: List[str]
    abstract: Optional[str]
    year: Optional[int]
    citation_count: Optional[int]
    doi: Optional[str]
    pdf_url: Optional[str]
    paper_url: Optional[str]
    source: str = "Unknown"


class SearchResponse(BaseModel):
    query_used: str
    results: List[PaperResult]
    total_found: int
    summary: Optional[str] = None


# ── LLM helpers ──────────────────────────────────────────────────────────────

def _extract_keywords(question: str) -> str:
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


def _generate_summary(question: str, papers: List[dict]) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=config.OPENAI_API_KEY)

    snippets = []
    for i, p in enumerate(papers[:8], 1):
        abstract = (p.get("abstract") or "No abstract available.")[:300]
        snippets.append(f"{i}. {p.get('title', 'Untitled')} ({p.get('year', '')})\n{abstract}")
    literature = "\n\n".join(snippets)

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a research assistant. Given a user's hypothesis and retrieved papers, "
                    "write a concise synthesis (3-5 sentences) that: "
                    "(1) summarises what the existing literature says, "
                    "(2) notes whether the evidence supports, contradicts, or is mixed, "
                    "(3) highlights important gaps or nuances. "
                    "Be direct and academic. Do not list papers by number."
                ),
            },
            {
                "role": "user",
                "content": f"Hypothesis: {question}\n\nRetrieved papers:\n{literature}",
            },
        ],
        temperature=0.3,
        max_tokens=300,
    )
    return resp.choices[0].message.content.strip()


# ── Source search functions ───────────────────────────────────────────────────

def _search_semantic_scholar(query: str, limit: int) -> List[dict]:
    params = {
        "query": query,
        "limit": min(limit, 20),
        "fields": SEMANTIC_SCHOLAR_FIELDS,
    }
    try:
        resp = requests.get(
            SEMANTIC_SCHOLAR_URL,
            params=params,
            headers={"User-Agent": "HypothesisApp/1.0"},
            timeout=15,
        )
        logger.info("Semantic Scholar: status=%d", resp.status_code)
        if resp.status_code == 429:
            logger.warning("Semantic Scholar rate limited")
            return []
        resp.raise_for_status()
        raw = resp.json().get("data", [])
    except Exception as e:
        logger.error("Semantic Scholar failed: %s", e)
        return []

    results = []
    for p in raw:
        ext_ids = p.get("externalIds") or {}
        pdf_info = p.get("openAccessPdf") or {}
        results.append({
            "title": p.get("title", "Untitled"),
            "authors": [a["name"] for a in (p.get("authors") or [])],
            "abstract": p.get("abstract"),
            "year": p.get("year"),
            "citation_count": p.get("citationCount"),
            "doi": ext_ids.get("DOI"),
            "pdf_url": pdf_info.get("url"),
            "paper_url": p.get("url"),
            "source": "Semantic Scholar",
        })
    return results


def _search_arxiv(query: str, limit: int) -> List[dict]:
    try:
        resp = requests.get(
            "http://export.arxiv.org/api/query",
            params={"search_query": f"all:{query}", "max_results": min(limit, 20), "sortBy": "relevance"},
            timeout=15,
        )
        logger.info("arXiv: status=%d", resp.status_code)
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
    except Exception as e:
        logger.error("arXiv failed: %s", e)
        return []

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    results = []
    for entry in root.findall("atom:entry", ns):
        title = (entry.findtext("atom:title", default="", namespaces=ns) or "").strip()
        abstract = (entry.findtext("atom:summary", default="", namespaces=ns) or "").strip()
        authors = [
            (a.findtext("atom:name", default="", namespaces=ns) or "").strip()
            for a in entry.findall("atom:author", ns)
        ]
        published = entry.findtext("atom:published", default="", namespaces=ns) or ""
        year = int(published[:4]) if published[:4].isdigit() else None
        paper_url = entry.findtext("atom:id", default="", namespaces=ns) or ""
        pdf_url = next(
            (lnk.get("href") for lnk in entry.findall("atom:link", ns)
             if lnk.get("type") == "application/pdf"),
            None,
        )
        results.append({
            "title": title,
            "authors": authors,
            "abstract": abstract or None,
            "year": year,
            "citation_count": None,
            "doi": None,
            "pdf_url": pdf_url,
            "paper_url": paper_url,
            "source": "arXiv",
        })
    return results


def _search_pubmed(query: str, limit: int) -> List[dict]:
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    try:
        search = requests.get(
            f"{base}/esearch.fcgi",
            params={"db": "pubmed", "term": query, "retmax": min(limit, 20), "retmode": "json"},
            timeout=15,
        )
        logger.info("PubMed search: status=%d", search.status_code)
        search.raise_for_status()
        ids = search.json().get("esearchresult", {}).get("idlist", [])
        if not ids:
            return []

        summary = requests.get(
            f"{base}/esummary.fcgi",
            params={"db": "pubmed", "id": ",".join(ids), "retmode": "json"},
            timeout=15,
        )
        summary.raise_for_status()
        data = summary.json().get("result", {})
    except Exception as e:
        logger.error("PubMed failed: %s", e)
        return []

    results = []
    for pmid in ids:
        p = data.get(pmid, {})
        pub_date = p.get("pubdate", "")
        year = int(pub_date[:4]) if pub_date[:4].isdigit() else None
        doi = next(
            (i.get("value") for i in p.get("articleids", []) if i.get("idtype") == "doi"),
            None,
        )
        results.append({
            "title": p.get("title", "Untitled"),
            "authors": [a.get("name", "") for a in p.get("authors", [])],
            "abstract": None,
            "year": year,
            "citation_count": None,
            "doi": doi,
            "pdf_url": None,
            "paper_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            "source": "PubMed",
        })
    return results


def _reconstruct_abstract(inverted_index: dict) -> Optional[str]:
    if not inverted_index:
        return None
    word_positions = [(pos, word) for word, positions in inverted_index.items() for pos in positions]
    word_positions.sort()
    return " ".join(word for _, word in word_positions)


def _search_openalex(query: str, limit: int) -> List[dict]:
    try:
        resp = requests.get(
            "https://api.openalex.org/works",
            params={
                "search": query,
                "per-page": min(limit, 25),
                "select": "title,authorships,abstract_inverted_index,publication_year,cited_by_count,doi,open_access,id",
            },
            headers={"User-Agent": "HypothesisApp/1.0"},
            timeout=15,
        )
        logger.info("OpenAlex: status=%d", resp.status_code)
        resp.raise_for_status()
        raw = resp.json().get("results", [])
    except Exception as e:
        logger.error("OpenAlex failed: %s", e)
        return []

    results = []
    for p in raw:
        doi_full = p.get("doi") or ""
        doi = doi_full.replace("https://doi.org/", "") or None
        oa = p.get("open_access") or {}
        authors = [
            a["author"]["display_name"]
            for a in (p.get("authorships") or [])
            if a.get("author")
        ]
        results.append({
            "title": p.get("title", "Untitled"),
            "authors": authors,
            "abstract": _reconstruct_abstract(p.get("abstract_inverted_index") or {}),
            "year": p.get("publication_year"),
            "citation_count": p.get("cited_by_count"),
            "doi": doi,
            "pdf_url": oa.get("oa_url"),
            "paper_url": p.get("id"),
            "source": "OpenAlex",
        })
    return results


# ── Deduplication ─────────────────────────────────────────────────────────────

def _normalise_title(title: str) -> str:
    return "".join(c.lower() for c in title if c.isalnum())


def _deduplicate(papers: List[dict]) -> List[dict]:
    seen_dois: set = set()
    seen_titles: set = set()
    unique = []
    for p in papers:
        doi = p.get("doi")
        norm = _normalise_title(p.get("title", ""))
        if doi and doi in seen_dois:
            continue
        if norm and norm in seen_titles:
            continue
        if doi:
            seen_dois.add(doi)
        if norm:
            seen_titles.add(norm)
        unique.append(p)
    return unique


# ── Endpoint ──────────────────────────────────────────────────────────────────

SOURCE_MAP = {
    "Semantic Scholar": _search_semantic_scholar,
    "arXiv": _search_arxiv,
    "PubMed": _search_pubmed,
    "OpenAlex": _search_openalex,
}


@router.post("/papers", response_model=SearchResponse)
def search_papers(req: SearchRequest):
    query = _extract_keywords(req.question)
    logger.info("Paper search: question=%r → query=%r", req.question, query)

    per_source = max(req.limit, 10)
    selected = [s for s in req.sources if s in SOURCE_MAP]
    if not selected:
        raise HTTPException(status_code=400, detail="No valid sources selected.")

    all_papers: List[dict] = []
    with ThreadPoolExecutor(max_workers=len(selected)) as executor:
        futures = {
            executor.submit(SOURCE_MAP[src], query, per_source): src
            for src in selected
        }
        for future in as_completed(futures):
            src = futures[future]
            try:
                all_papers.extend(future.result())
            except Exception as e:
                logger.error("Source %s raised: %s", src, e)

    unique = _deduplicate(all_papers)
    # Sort: prefer papers with abstracts and citation counts
    unique.sort(key=lambda p: (p.get("abstract") is None, -(p.get("citation_count") or 0)))
    unique = unique[: req.limit * 2]

    results = [PaperResult(**p) for p in unique]
    summary = _generate_summary(req.question, [p for p in unique if p.get("abstract")])

    return SearchResponse(
        query_used=query,
        results=results,
        total_found=len(results),
        summary=summary,
    )
