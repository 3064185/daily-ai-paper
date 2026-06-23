"""
Open-access full-text reading for papers.
Downloads PDFs and extracts text; falls back to abstract when unavailable.
"""
import logging
import re
import tempfile
from pathlib import Path
from typing import Optional

import httpx

from config import REQUEST_TIMEOUT, DOWNLOAD_OPEN_ACCESS_PDFS, MAX_PDF_ATTACHMENT_MB, USE_SYSTEM_PROXY

logger = logging.getLogger("fulltext")


def _client() -> httpx.Client:
    kwargs = dict(timeout=httpx.Timeout(REQUEST_TIMEOUT), follow_redirects=True)
    if not USE_SYSTEM_PROXY:
        kwargs["proxy"] = None
    return httpx.Client(**kwargs)


def _is_open_access(pdf_url: str) -> bool:
    return bool(pdf_url) and pdf_url.startswith("http")


def _download_pdf(url: str, max_mb: int = MAX_PDF_ATTACHMENT_MB) -> Optional[bytes]:
    """Download a PDF, returns raw bytes if successful and within size limit."""
    try:
        with _client() as c:
            r = c.get(url)
            r.raise_for_status()
        content = r.content
        size_mb = len(content) / (1024 * 1024)
        if size_mb > max_mb:
            logger.debug("PDF too large: %.1f MB > %d MB limit", size_mb, max_mb)
            return None
        # Quick check it's actually a PDF
        if not content.startswith(b"%PDF"):
            logger.debug("Not a valid PDF header")
            return None
        return content
    except Exception as exc:
        logger.debug("PDF download failed for %s: %s", url, exc)
    return None


def _extract_text_from_pdf(pdf_bytes: bytes) -> Optional[str]:
    """Extract text from PDF bytes using PyMuPDF fallback chain."""
    # Try PyMuPDF (fitz) first
    try:
        import fitz
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
        if text.strip():
            return text[:15000]  # cap at ~15k chars
    except ImportError:
        pass
    except Exception as exc:
        logger.debug("PyMuPDF extraction failed: %s", exc)

    # Fallback: pdfminer
    try:
        from io import BytesIO
        from pdfminer.high_level import extract_text as pdfminer_extract
        text = pdfminer_extract(BytesIO(pdf_bytes))
        if text.strip():
            return text[:15000]
    except ImportError:
        pass
    except Exception as exc:
        logger.debug("pdfminer extraction failed: %s", exc)

    # Fallback: pypdf
    try:
        from io import BytesIO
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(pdf_bytes))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        if text.strip():
            return text[:15000]
    except ImportError:
        pass
    except Exception as exc:
        logger.debug("pypdf extraction failed: %s", exc)

    return None


def read_paper(paper: dict) -> dict:
    """Read a paper's full text if open access. Returns enriched paper dict."""
    paper = dict(paper)  # copy
    pdf_url = paper.get("pdf_url", "")
    abstract = paper.get("abstract", "")

    paper["full_text"] = ""
    paper["full_text_source"] = "abstract_only"

    if pdf_url and _is_open_access(pdf_url) and DOWNLOAD_OPEN_ACCESS_PDFS:
        pdf_bytes = _download_pdf(pdf_url)
        if pdf_bytes:
            text = _extract_text_from_pdf(pdf_bytes)
            if text and len(text) > len(abstract):
                paper["full_text"] = text
                paper["full_text_source"] = "pdf"
                # Clean up whitespace
                paper["full_text"] = re.sub(r"\s+", " ", paper["full_text"]).strip()
                logger.debug("Full text extracted for %s …", paper.get("title", "")[:60])
                return paper

    # Fallback: use abstract as full_text proxy
    paper["full_text"] = abstract
    paper["full_text_source"] = "abstract_only"
    return paper


def read_papers(papers: list[dict]) -> list[dict]:
    """Batch read full text for all papers with OA PDFs."""
    results = []
    for paper in papers:
        try:
            paper = read_paper(paper)
        except Exception as exc:
            logger.warning("Full-text reading failed for %s: %s", paper.get("title", "")[:60], exc)
            paper["full_text"] = paper.get("abstract", "")
            paper["full_text_source"] = "abstract_only"
        results.append(paper)
    logger.info("Full-text reading: %d/%d have PDF full text",
                sum(1 for p in results if p.get("full_text_source") == "pdf"), len(results))
    return results
