"""
Open-access full-text reading for papers with selective downloading:
- Only reads full text for top 3-5 highest-scored papers
- Concurrent download with ThreadPoolExecutor (max 2-3)
- Per-PDF timeout (30s)
- Extracts only key sections (Abstract, Introduction, Method, etc.)
- Falls back to abstract only for all other papers
"""
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import httpx

from config import REQUEST_TIMEOUT, DOWNLOAD_OPEN_ACCESS_PDFS, MAX_PDF_ATTACHMENT_MB, USE_SYSTEM_PROXY

logger = logging.getLogger("fulltext")

# ── Config ──────────────────────────────────────────────────────────
MAX_FULL_TEXT_PAPERS = 5        # max papers to attempt full-text downloading
MIN_SCORE_FOR_FULL_TEXT = 4     # minimum relevance score
PDF_TIMEOUT_SECONDS = 30        # per-PDF download timeout
PDF_CONCURRENCY = 3             # max concurrent PDF downloads

# Key sections to extract from PDFs (case-insensitive)
KEY_SECTIONS = [
    "abstract", "introduction", "method", "methodology",
    "experiment", "experiments", "results", "result",
    "conclusion", "discussion",
]


def _build_client(timeout: int = PDF_TIMEOUT_SECONDS) -> httpx.Client:
    kwargs = dict(timeout=httpx.Timeout(timeout), follow_redirects=True)
    if not USE_SYSTEM_PROXY:
        kwargs["proxy"] = None
    return httpx.Client(**kwargs)


def _is_open_access(pdf_url: str) -> bool:
    return bool(pdf_url) and pdf_url.startswith("http")


def select_papers_for_full_text(papers: list[dict]) -> tuple[list[dict], int]:
    """Select papers for full-text reading based on relevance score.
    Returns (papers_with_fulltext_flag, skipped_count)."""
    # Papers that already have relevance_score
    scored = [p for p in papers if p.get("relevance_score", 0) is not None]
    scored.sort(key=lambda p: p.get("relevance_score", 0), reverse=True)

    # Top N papers with score >= threshold
    selected = [p for p in scored if p.get("relevance_score", 0) >= MIN_SCORE_FOR_FULL_TEXT][:MAX_FULL_TEXT_PAPERS]
    selected_titles = {p.get("title", "") for p in selected}

    # Flag all papers
    for p in papers:
        if p.get("title", "") in selected_titles:
            p["_download_full_text"] = True
        else:
            p["_download_full_text"] = False

    skip_count = len(papers) - len(selected)
    logger.info("Selected %d papers for full-text reading (skipped %d with low score)",
                len(selected), skip_count)
    return selected, skip_count


def _download_single_pdf(paper: dict) -> dict:
    """Download a single PDF with timeout and size check."""
    paper = dict(paper)
    pdf_url = paper.get("pdf_url", "")
    title = paper.get("title", "")[:80]
    result = {"paper_idx": id(paper), "success": False, "reason": "", "pdf_bytes": None}

    if not pdf_url or not _is_open_access(pdf_url):
        result["reason"] = "no_open_access_url"
        return result

    try:
        with _build_client() as client:
            r = client.get(pdf_url)
            r.raise_for_status()
            if r.history:
                logger.debug("PDF download redirect for '%s': %s", title,
                             [str(h.url) for h in r.history])
        content = r.content
        size_mb = len(content) / (1024 * 1024)

        if not content.startswith(b"%PDF"):
            result["reason"] = "not_a_valid_pdf"
            logger.debug("PDF '%s' has invalid header", title)
            return result

        if size_mb > MAX_PDF_ATTACHMENT_MB:
            result["reason"] = f"too_large_{size_mb:.1f}MB"
            logger.debug("PDF '%s' too large: %.1f MB > %d MB", title, size_mb, MAX_PDF_ATTACHMENT_MB)
            return result

        result["success"] = True
        result["pdf_bytes"] = content
        logger.info("PDF downloaded for '%s' (%.1f MB)", title, size_mb)
        return result

    except httpx.TimeoutException:
        result["reason"] = f"timeout_{PDF_TIMEOUT_SECONDS}s"
        logger.warning("PDF download timed out for '%s' (%ds)", title, PDF_TIMEOUT_SECONDS)
    except Exception as exc:
        result["reason"] = f"download_error: {exc}"
        logger.debug("PDF download failed for '%s': %s", title, exc)

    return result


def _extract_text_from_pdf(pdf_bytes: bytes) -> Optional[str]:
    """Extract text from PDF bytes using PyMuPDF fallback chain."""
    try:
        import fitz
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
        if text.strip():
            return text[:20000]
    except ImportError:
        pass
    except Exception as exc:
        logger.debug("PyMuPDF extraction failed: %s", exc)

    try:
        from io import BytesIO
        from pdfminer.high_level import extract_text as pdfminer_extract
        text = pdfminer_extract(BytesIO(pdf_bytes))
        if text.strip():
            return text[:20000]
    except ImportError:
        pass
    except Exception as exc:
        logger.debug("pdfminer extraction failed: %s", exc)

    try:
        from io import BytesIO
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(pdf_bytes))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        if text.strip():
            return text[:20000]
    except ImportError:
        pass
    except Exception as exc:
        logger.debug("pypdf extraction failed: %s", exc)

    return None


def _extract_key_sections(full_text: str) -> str:
    """Extract only key sections (Abstract, Introduction, Method, etc.) from full text."""
    if not full_text:
        return ""
    
    lines = full_text.split("\n")
    section_map = {}  # section_idx -> [lines]
    current_section = "preamble"
    current_lines = []

    for line in lines:
        stripped = line.strip().lower()
        # Detect section headers (e.g., "1. Introduction", "Abstract", "Methodology")
        detected = False
        for keyword in KEY_SECTIONS:
            # Match patterns like: "Abstract", "1. Introduction", "2. Method", "III. Results"
            if (stripped == keyword or
                stripped.startswith(keyword) or
                re.match(rf"^(i{0,3}v?x?\.?\s*{keyword}|[0-9]+\.?\s*{keyword}|[a-vx-z]\.?\s*{keyword})$", stripped)):
                section_map[current_section] = current_lines
                current_section = keyword
                current_lines = [line]
                detected = True
                break
        
        if not detected:
            current_lines.append(line)
    
    section_map[current_section] = current_lines

    # Reconstruct: keep only key sections + a bit of preamble
    result_parts = []
    for section_name, section_lines in section_map.items():
        if section_name in KEY_SECTIONS or section_name == "preamble":
            text = "\n".join(section_lines).strip()
            if len(text) > 50:  # skip empty/minimal sections
                result_parts.append(f"[{section_name.capitalize()}]\n{text[:3000]}")

    result = "\n\n".join(result_parts)
    return result[:15000]


def read_paper_fulltext(paper: dict) -> dict:
    """Full text reading for a single paper. Returns enriched paper dict with section extraction."""
    paper = dict(paper)
    pdf_url = paper.get("pdf_url", "")
    abstract = paper.get("abstract", "")
    
    paper["full_text"] = ""
    paper["full_text_source"] = "abstract_only"
    paper["full_text_sections"] = ""
    paper["full_text_error"] = ""

    if not (pdf_url and _is_open_access(pdf_url) and DOWNLOAD_OPEN_ACCESS_PDFS):
        paper["full_text_source"] = "abstract_only"
        paper["full_text_error"] = "no_open_access_url"
        paper["full_text"] = abstract
        return paper

    result = _download_single_pdf(paper)
    if not result.get("success"):
        paper["full_text_source"] = "abstract_only_low"
        paper["full_text_error"] = result.get("reason", "unknown")
        paper["full_text"] = abstract
        logger.debug("Full-text skipped for '%s': %s", paper.get("title", "")[:60], result.get("reason"))
        return paper

    text = _extract_text_from_pdf(result["pdf_bytes"])
    if not text:
        paper["full_text_source"] = "abstract_only_low"
        paper["full_text_error"] = "extraction_failed"
        paper["full_text"] = abstract
        return paper

    # Extract key sections, then cap total
    sections_text = _extract_key_sections(text)
    paper["full_text_sections"] = sections_text
    paper["full_text"] = re.sub(r"\s+", " ", text).strip()[:15000]
    paper["full_text_source"] = "pdf"
    paper["full_text_error"] = ""
    logger.info("Full text extracted for '%s' (sections: %d chars)",
                paper.get("title", "")[:60], len(sections_text))
    return paper


def read_papers(papers: list, papers_for_fulltext: Optional[list] = None) -> list:
    """Batch read full text for selected papers using concurrent download.
    
    Args:
        papers: All papers
        papers_for_fulltext: Subset of papers to attempt full-text reading.
                            If None, uses _download_full_text flag.
    """
    results = []
    fulltext_stats = {"full_pdf": 0, "abstract_only": 0, "abstract_only_low": 0, "failed": 0}
    
    # Determine which papers need full-text download
    if papers_for_fulltext is None:
        papers_for_fulltext = [p for p in papers if p.get("_download_full_text", False)]
    fulltext_titles = {p.get("title", "") for p in papers_for_fulltext}

    # Phase 1: concurrently download PDFs for selected papers
    download_results = {}
    if papers_for_fulltext:
        logger.info("Starting concurrent PDF download for %d papers (concurrency=%d)",
                    len(papers_for_fulltext), PDF_CONCURRENCY)
        with ThreadPoolExecutor(max_workers=PDF_CONCURRENCY) as executor:
            future_map = {executor.submit(_download_single_pdf, p): p for p in papers_for_fulltext}
            for future in as_completed(future_map):
                p = future_map[future]
                try:
                    result = future.result()
                    download_results[p.get("title", "")] = result
                except Exception as exc:
                    download_results[p.get("title", "")] = {
                        "success": False, "reason": f"thread_error: {exc}", "pdf_bytes": None
                    }

    # Phase 2: process all papers
    for paper in papers:
        try:
            title = paper.get("title", "")
            p = dict(paper)

            if title in fulltext_titles and title in download_results:
                dl_result = download_results[title]
                if dl_result.get("success"):
                    text = _extract_text_from_pdf(dl_result["pdf_bytes"])
                    if text:
                        sections_text = _extract_key_sections(text)
                        p["full_text_sections"] = sections_text
                        p["full_text"] = re.sub(r"\s+", " ", text).strip()[:15000]
                        p["full_text_source"] = "pdf"
                        p["full_text_error"] = ""
                        fulltext_stats["full_pdf"] += 1
                    else:
                        p["full_text"] = paper.get("abstract", "")
                        p["full_text_source"] = "abstract_only_low"
                        p["full_text_error"] = dl_result.get("reason", "extraction_failed")
                        fulltext_stats["abstract_only_low"] += 1
                else:
                    p["full_text"] = paper.get("abstract", "")
                    p["full_text_source"] = "abstract_only_low"
                    p["full_text_error"] = dl_result.get("reason", "unknown")
                    fulltext_stats["abstract_only_low"] += 1
            else:
                # Not selected for full text - use abstract
                p["full_text"] = paper.get("abstract", "")
                p["full_text_source"] = "abstract_only"
                p["full_text_error"] = "not_selected"
                fulltext_stats["abstract_only"] += 1

            results.append(p)
        except Exception as exc:
            logger.warning("Full-text processing failed for '%s': %s",
                          paper.get("title", "")[:60], exc)
            p = dict(paper)
            p["full_text"] = paper.get("abstract", "")
            p["full_text_source"] = "abstract_only"
            p["full_text_error"] = f"processing_error: {exc}"
            results.append(p)
            fulltext_stats["failed"] += 1

    logger.info("Full-text summary: %d full PDFs, %d abstract_only, %d abstract_only_low, %d failed",
                fulltext_stats["full_pdf"], fulltext_stats["abstract_only"],
                fulltext_stats["abstract_only_low"], fulltext_stats["failed"])
    return results
