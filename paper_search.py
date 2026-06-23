"""
Multi-source paper search with independent error handling per source.
Sources: arXiv, Semantic Scholar, OpenAlex, Crossref, DBLP, Papers with Code.
"""
import logging
import re
import time
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from config import (
    REQUEST_TIMEOUT, MAX_PAPERS_PER_SOURCE, USE_SYSTEM_PROXY,
    SEMANTIC_SCHOLAR_API_KEY, OPENALEX_EMAIL,
)

logger = logging.getLogger("papers")

# Shared HTTP client factory
def _client(**kw) -> httpx.Client:
    kwargs = dict(follow_redirects=True)
    kwargs.update(kw)
    if not USE_SYSTEM_PROXY:
        kwargs["proxy"] = None
    return httpx.Client(**kwargs)


def _today() -> date:
    from config import RUN_DATE
    return RUN_DATE or date.today()


def _safe_text(val) -> str:
    return str(val or "").strip()


###############################################################################
#  arXiv
###############################################################################
def search_arxiv(target_date: date) -> list[dict]:
    """Search arXiv via their API for cs.AI, cs.LG, cs.CL, cs.CV, cs.RO."""
    logger.info("Searching arXiv for %s …", target_date.isoformat())
    papers = []
    categories = ["cs.AI", "cs.LG", "cs.CL", "cs.CV", "cs.RO"]
    for cat in categories:
        try:
            url = (
                f"http://export.arxiv.org/api/query?"
                f"search_query=cat:{cat}"
                f"&start=0&max_results={MAX_PAPERS_PER_SOURCE // len(categories) + 1}"
                f"&sortBy=submittedDate&sortOrder=descending"
            )
            # ArXiv uses 301 redirects - this is normal
            with _client(timeout=httpx.Timeout(REQUEST_TIMEOUT, connect=15, read=25)) as c:
                r = c.get(url)
                r.raise_for_status()
                if r.history:
                    logger.debug("ArXiv redirect chain: %s", [str(h.url) for h in r.history])
            import feedparser
            feed = feedparser.parse(r.text)
            for entry in feed.entries:
                title = _safe_text(entry.get("title", ""))
                summary = re.sub(r"\s+", " ", _safe_text(entry.get("summary", "")))
                link = entry.get("id", "")
                arxiv_id = link.split("/abs/")[-1] if "/abs/" in link else ""
                authors = [a.get("name", "") for a in entry.get("authors", [])]
                published = _safe_text(entry.get("published", ""))[:10]
                papers.append({
                    "title": title,
                    "abstract": summary[:2000],
                    "authors": authors,
                    "url": link,
                    "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}.pdf" if arxiv_id else "",
                    "arxiv_id": arxiv_id,
                    "published": published,
                    "source": "arXiv",
                    "source_category": cat,
                })
        except httpx.TimeoutException:
            logger.warning("arXiv / %s timed out", cat)
        except Exception as exc:
            logger.warning("arXiv / %s failed: %s", cat, exc)
    logger.info("arXiv returned %d papers", len(papers))
    return papers


###############################################################################
#  Semantic Scholar
###############################################################################
def search_semantic_scholar(target_date: date) -> list[dict]:
    """Search Semantic Scholar recent papers API."""
    logger.info("Searching Semantic Scholar for %s …", target_date.isoformat())
    papers = []
    try:
        headers = {"Accept": "application/json"}
        if SEMANTIC_SCHOLAR_API_KEY:
            headers["x-api-key"] = SEMANTIC_SCHOLAR_API_KEY
        url = (
            "https://api.semanticscholar.org/graph/v1/paper/search"
            "?query=artificial+intelligence+machine+learning"
            f"&limit={MAX_PAPERS_PER_SOURCE}"
            "&fields=title,abstract,authors,url,externalIds,publicationDate,openAccessPdf"
        )
        with _client(timeout=httpx.Timeout(REQUEST_TIMEOUT, connect=10, read=25)) as c:
            r = c.get(url, headers=headers)
            r.raise_for_status()
        data = r.json()
        for item in data.get("data", []):
            ext_ids = item.get("externalIds") or {}
            papers.append({
                "title": _safe_text(item.get("title")),
                "abstract": _safe_text(item.get("abstract", ""))[:2000],
                "authors": [a.get("name", "") for a in (item.get("authors") or [])],
                "url": _safe_text(item.get("url")),
                "pdf_url": (item.get("openAccessPdf") or {}).get("url", ""),
                "arxiv_id": ext_ids.get("ArXiv", ""),
                "published": _safe_text(item.get("publicationDate", ""))[:10],
                "source": "Semantic Scholar",
            })
    except httpx.TimeoutException:
        logger.warning("Semantic Scholar timed out")
    except Exception as exc:
        logger.warning("Semantic Scholar failed: %s", exc)
    logger.info("Semantic Scholar returned %d papers", len(papers))
    return papers


###############################################################################
#  OpenAlex
###############################################################################
def search_openalex(target_date: date) -> list[dict]:
    """Search OpenAlex for recent AI/ML works."""
    logger.info("Searching OpenAlex for %s …", target_date.isoformat())
    papers = []
    try:
        headers = {"Accept": "application/json"}
        if OPENALEX_EMAIL:
            headers["User-Agent"] = f"mailto:{OPENALEX_EMAIL}"
        concepts = "C154945302,C263385678"
        url = (
            f"https://api.openalex.org/works"
            f"?filter=concepts.id:{concepts}"
            f"&sort=publication_date:desc"
            f"&per_page={min(MAX_PAPERS_PER_SOURCE, 50)}"
            "&select=id,title,abstract_inverted_index,authorships,primary_location,open_access,publication_date,cited_by_count"
        )
        with _client(timeout=httpx.Timeout(REQUEST_TIMEOUT, connect=10, read=25)) as c:
            r = c.get(url, headers=headers)
            r.raise_for_status()
        data = r.json()
        for item in data.get("results", []):
            abs_index = item.get("abstract_inverted_index") or {}
            if abs_index:
                words = []
                for word, positions in abs_index.items():
                    for pos in positions:
                        words.append((pos, word))
                words.sort()
                abstract = " ".join(w for _, w in words)
            else:
                abstract = ""
            loc = item.get("primary_location") or {}
            source = loc.get("source") or {}
            pdf_url = ""
            oa = item.get("open_access") or {}
            if oa.get("is_oa") and oa.get("oa_url"):
                pdf_url = oa["oa_url"]
            papers.append({
                "title": _safe_text(item.get("title")),
                "abstract": abstract[:2000],
                "authors": [a.get("author", {}).get("display_name", "") for a in (item.get("authorships") or [])],
                "url": f"https://openalex.org/{item.get('id','').split('/')[-1]}" if item.get("id") else "",
                "pdf_url": pdf_url,
                "published": _safe_text(item.get("publication_date", ""))[:10],
                "source": "OpenAlex",
                "venue": _safe_text(source.get("display_name", "")),
                "cited_by": item.get("cited_by_count", 0),
            })
    except httpx.TimeoutException:
        logger.warning("OpenAlex timed out")
    except Exception as exc:
        logger.warning("OpenAlex failed: %s", exc)
    logger.info("OpenAlex returned %d papers", len(papers))
    return papers


###############################################################################
#  Crossref
###############################################################################
def search_crossref(target_date: date) -> list[dict]:
    """Search Crossref for recent AI/CS works."""
    logger.info("Searching Crossref for %s …", target_date.isoformat())
    papers = []
    try:
        url = (
            "https://api.crossref.org/works"
            f"?query=artificial+intelligence+machine+learning"
            f"&filter=type:journal-article,from-pub-date:{(target_date - timedelta(days=7)).isoformat()}"
            f"&rows={MAX_PAPERS_PER_SOURCE}"
            "&sort=published&order=desc"
        )
        with _client(timeout=httpx.Timeout(REQUEST_TIMEOUT, connect=10, read=25)) as c:
            r = c.get(url)
            r.raise_for_status()
        data = r.json()
        for item in data.get("message", {}).get("items", []):
            papers.append({
                "title": _safe_text(item.get("title", [""])[0]),
                "abstract": _safe_text(item.get("abstract", ""))[:2000],
                "authors": [a.get("given", "") + " " + a.get("family", "") for a in (item.get("author") or [])],
                "url": (item.get("URL") or ""),
                "pdf_url": "",
                "published": _safe_text(item.get("created", {}).get("date-time", ""))[:10],
                "source": "Crossref",
                "doi": _safe_text(item.get("DOI", "")),
            })
    except httpx.TimeoutException:
        logger.warning("Crossref timed out")
    except Exception as exc:
        logger.warning("Crossref failed: %s", exc)
    logger.info("Crossref returned %d papers", len(papers))
    return papers


###############################################################################
#  DBLP
###############################################################################
def search_dblp(target_date: date) -> list[dict]:
    """Search DBLP for recent AI/CS publications."""
    logger.info("Searching DBLP for %s …", target_date.isoformat())
    papers = []
    queries = [
        "artificial+intelligence",
        "machine+learning",
        "large+language+model",
        "computer+vision",
    ]
    seen = set()
    for q in queries:
        try:
            url = f"https://dblp.org/search/publ/api?q={q}&h={MAX_PAPERS_PER_SOURCE // len(queries) + 1}&format=json"
            with _client(timeout=httpx.Timeout(REQUEST_TIMEOUT, connect=10, read=25)) as c:
                r = c.get(url)
                r.raise_for_status()
            data = r.json()
            hits = data.get("result", {}).get("hits", {}).get("hit", [])
            for hit in hits:
                info = hit.get("info", {})
                title = _safe_text(info.get("title", ""))
                dedup_key = title.lower()[:80]
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)
                authors_el = info.get("authors", {})
                authors_list = authors_el.get("author", [])
                if isinstance(authors_list, dict):
                    authors_list = [authors_list]
                authors = [a.get("text", "") for a in authors_list]
                year = str(info.get("year", ""))
                papers.append({
                    "title": title,
                    "abstract": "",
                    "authors": authors,
                    "url": _safe_text(info.get("url", "")),
                    "pdf_url": "",
                    "published": year,
                    "source": "DBLP",
                    "venue": _safe_text(info.get("venue", "")),
                })
        except httpx.TimeoutException:
            logger.warning("DBLP / %s timed out", q)
        except Exception as exc:
            logger.warning("DBLP / %s failed: %s", q, exc)
    logger.info("DBLP returned %d papers", len(papers))
    return papers


###############################################################################
#  Papers with Code (Hugging Face trending)
###############################################################################
def search_papers_with_code(target_date: date) -> list[dict]:
    """Scrape Hugging Face daily papers for trending ML/AI papers.
    Has exponential backoff retry with independent timeout.
    Failure of this source won't block the pipeline."""
    logger.info("Searching Hugging Face papers for %s …", target_date.isoformat())
    papers = []
    
    url = "https://huggingface.co/papers"
    max_retries = 2
    last_error = ""
    
    for attempt in range(max_retries + 1):
        try:
            # Independent shorter timeout for HF
            timeout = httpx.Timeout(30, connect=10, read=20)
            with _client(timeout=timeout) as c:
                r = c.get(url)
                r.raise_for_status()
            
            soup = BeautifulSoup(r.text, "lxml")
            for card in soup.select("article") or soup.select("[data-testid='paper-card']") or soup.select("li"):
                title_el = card.select_one("h3") or card.select_one("h2") or card.select_one("a")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                link_el = card.select_one("a[href*='/papers/']")
                link = "https://huggingface.co" + link_el["href"] if link_el else ""
                abstract_el = card.select_one("p") or card.select_one(".prose")
                abstract = _safe_text(abstract_el.get_text(strip=True)[:500] if abstract_el else "")
                papers.append({
                    "title": title,
                    "abstract": abstract[:2000],
                    "authors": [],
                    "url": link,
                    "pdf_url": "",
                    "published": target_date.isoformat(),
                    "source": "Papers with Code (HF)",
                })
            papers = papers[:MAX_PAPERS_PER_SOURCE]
            logger.info("Hugging Face papers returned %d papers", len(papers))
            return papers
            
        except httpx.TimeoutException:
            last_error = f"Hugging Face timed out (connect=10s, read=20s)"
            logger.warning("%s, attempt %d/%d", last_error, attempt + 1, max_retries + 1)
        except Exception as exc:
            last_error = str(exc)
            logger.warning("Hugging Face attempt %d/%d failed: %s", attempt + 1, max_retries + 1, exc)
        
        if attempt < max_retries:
            delay = 2 ** attempt * 2  # 2s, 4s exponential backoff
            logger.info("Retrying Hugging Face in %ds…", delay)
            time.sleep(delay)
    
    logger.warning("Hugging Face exhausted %d retries: %s", max_retries, last_error)
    return papers


###############################################################################
#  Orchestrator
###############################################################################
SOURCE_REGISTRY = [
    ("arXiv", search_arxiv),
    ("Semantic Scholar", search_semantic_scholar),
    ("OpenAlex", search_openalex),
    ("Crossref", search_crossref),
    ("DBLP", search_dblp),
    ("Papers with Code (HF)", search_papers_with_code),
]


def search_all() -> tuple[list[dict], list[dict]]:
    """Search all sources. Returns (all_papers, source_statuses)."""
    target_date = _today()
    all_papers = []
    source_statuses = []

    for name, func in SOURCE_REGISTRY:
        try:
            papers = func(target_date) or []
            status = "success" if papers else "no_results"
            all_papers.extend(papers)
            logger.info("%s: %d papers, status=%s", name, len(papers), status)
        except Exception as exc:
            status = f"error: {exc}"
            logger.warning("%s failed entirely: %s", name, exc)
        source_statuses.append({"source": name, "count": len([p for p in all_papers if p.get("source") == name]) if status.startswith("success") else 0, "status": status})

    # Recompute counts properly
    from collections import Counter
    src_counts = Counter(p.get("source", "unknown") for p in all_papers)
    for s in source_statuses:
        s["count"] = src_counts.get(s["source"], 0)

    logger.info("Total papers from all sources: %d", len(all_papers))
    return all_papers, source_statuses
