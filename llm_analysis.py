"""
LLM-based structured analysis of papers using OpenAI.
Falls back to rule-based analysis when unavailable.
Supports OpenAI and DeepSeek via OPENAI_BASE_URL.
"""
import json
import logging
import re
from typing import Optional

from openai import OpenAI

from config import OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL

logger = logging.getLogger("llm")

# ── System prompt ─────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a research assistant analyzing CS/AI papers for a Chinese daily digest.

For each paper, produce a JSON object with these fields:
- "relevance_score": 1-10 (how relevant to current AI/ML research)
- "innovation_type": "algorithm", "system", "theory", "application", "benchmark", "survey", or "other"
- "key_contribution": one sentence in Chinese describing the main contribution
- "key_method": one sentence in Chinese describing the methodology
- "strengths": 1-2 bullet points in Chinese
- "limitations": 1 bullet point in Chinese if identifiable, or ""
- "target_audience": "researchers", "engineers", "both", or "general"

Only output valid JSON, no markdown fences or preamble."""


def _build_client() -> Optional[OpenAI]:
    if not OPENAI_API_KEY:
        return None
    kwargs = {"api_key": OPENAI_API_KEY}
    if OPENAI_BASE_URL:
        kwargs["base_url"] = OPENAI_BASE_URL
    return OpenAI(**kwargs)


def analyze_paper_openai(title: str, abstract: str, full_text: str = "") -> Optional[dict]:
    """Analyze a single paper using OpenAI."""
    client = _build_client()
    if not client:
        return None

    text_for_analysis = full_text if len(full_text) > len(abstract) else abstract
    # Truncate to avoid token overflow
    text_for_analysis = text_for_analysis[:8000]

    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Title: {title}\n\nText: {text_for_analysis}"},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=500,
        )
        content = response.choices[0].message.content
        return json.loads(content)
    except Exception as exc:
        logger.debug("OpenAI analysis failed for '%s': %s", title[:50], exc)
    return None


def rule_based_score(paper: dict) -> int:
    """Fallback rule-based relevance scoring (1-10)."""
    score = 5
    text = (paper.get("title", "") + " " + paper.get("abstract", "")).lower()

    # Highly relevant keywords
    high_impact = ["large language model", "llm", "gpt", "transformer", "diffusion",
                   "reinforcement learning", "foundation model", "multi-modal",
                   "multimodal", "agent", "reasoning", "chain-of-thought"]
    for kw in high_impact:
        if kw in text:
            score += 1
            break

    # Top venues
    venue = (paper.get("venue", "") or "").lower()
    top_venues = ["nature", "science", "cell", "neurips", "icml", "iclr", "cvpr",
                  "acl", "emnlp", "aaai", "pnas"]
    for v in top_venues:
        if v in venue:
            score += 2
            break

    # Citations boost (if available)
    cited_by = paper.get("cited_by", 0)
    if isinstance(cited_by, (int, float)) and cited_by > 100:
        score += 1

    # Penalize very short abstracts (likely not a full paper)
    if len(paper.get("abstract", "")) < 50:
        score -= 1

    return max(1, min(10, score))


def analyze_paper(paper: dict) -> dict:
    """Full analysis: try OpenAI first, fallback to rule-based."""
    paper = dict(paper)
    llm_analysis = analyze_paper_openai(
        paper.get("title", ""),
        paper.get("abstract", ""),
        paper.get("full_text", ""),
    )

    if llm_analysis:
        paper["relevance_score"] = llm_analysis.get("relevance_score", 5)
        paper["innovation_type"] = llm_analysis.get("innovation_type", "")
        paper["key_contribution"] = llm_analysis.get("key_contribution", "")
        paper["key_method"] = llm_analysis.get("key_method", "")
        paper["strengths"] = llm_analysis.get("strengths", "")
        paper["limitations"] = llm_analysis.get("limitations", "")
        paper["target_audience"] = llm_analysis.get("target_audience", "")
        paper["analysis_method"] = "openai"
    else:
        paper["relevance_score"] = rule_based_score(paper)
        paper["innovation_type"] = ""
        paper["key_contribution"] = ""
        paper["key_method"] = ""
        paper["strengths"] = ""
        paper["limitations"] = ""
        paper["target_audience"] = ""
        paper["analysis_method"] = "rule"
    return paper


def analyze_papers(papers: list[dict]) -> list[dict]:
    """Batch analyze all papers."""
    results = []
    for paper in papers:
        try:
            paper = analyze_paper(paper)
        except Exception as exc:
            logger.warning("Analysis failed for '%s': %s", paper.get("title", "")[:50], exc)
            paper["relevance_score"] = rule_based_score(paper)
            paper["analysis_method"] = "rule_fallback"
        results.append(paper)
    logger.info("LLM analysis: %d OpenAI, %d rule-based",
                sum(1 for p in results if p.get("analysis_method") == "openai"), 
                sum(1 for p in results if p.get("analysis_method") != "openai"))
    return results
