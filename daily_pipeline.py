#!/usr/bin/env python3
"""
Daily AI News & Paper Digest Pipeline — main entry point.

Usage:
    python daily_pipeline.py                # today, no email
    python daily_pipeline.py --send-email   # today, send email
    python daily_pipeline.py --date 2026-06-21 --no-email
"""

import argparse
import logging
import os
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import config

LOG_DIR = Path(__file__).parent / "logs"

def setup_logging(date_str: str):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / f"daily_run_{date_str}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    return logging.getLogger("pipeline")


def load_env():
    """Load .env file if present."""
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        for line in env_path.read_text("utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip("\"'")
            os.environ.setdefault(key, val)


def get_today() -> date:
    from config import RUN_DATE
    return RUN_DATE or date.today()


def run_pipeline(send_email: bool = False) -> bool:
    """Run the full pipeline. Returns True if core report succeeded."""
    today = get_today()
    date_str = today.strftime("%Y%m%d")
    logger = logging.getLogger("pipeline")
    timings = {}
    pipeline_ok = True

    logger.info("=" * 60)
    logger.info("Daily Pipeline starting for %s", today.isoformat())
    logger.info("Send email: %s", send_email)
    logger.info("=" * 60)

    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── Step 1: AIHOT News ──
    t0 = time.time()
    news_items = []
    news_status = "success"
    try:
        import aihot_scraper
        news_items = aihot_scraper.scrape()
        logger.info("AIHOT news: %d items", len(news_items))
    except Exception as exc:
        news_status = f"error: {exc}"
        logger.error("AIHOT scraper failed: %s", exc)
    timings["news_scrape"] = time.time() - t0

    # ── Step 2: Paper search ──
    t0 = time.time()
    all_papers = []
    source_statuses = []
    try:
        import paper_search
        all_papers, source_statuses = paper_search.search_all()
        logger.info("Total papers: %d from %d sources",
                     len(all_papers), len(source_statuses))
    except Exception as exc:
        logger.error("Paper search failed: %s", exc)
        source_statuses = [{"source": "all", "count": 0, "status": f"error: {exc}"}]
        pipeline_ok = False
    timings["paper_search"] = time.time() - t0

    # ── Step 3: Rule-based scoring (quick pass) ──
    t0 = time.time()
    try:
        import llm_analysis
        # First pass: rule-based score to decide which papers get full-text
        for paper in all_papers:
            if paper.get("relevance_score") is None:
                paper["relevance_score"] = llm_analysis.rule_based_score(paper)
        logger.info("Rule-based scoring complete for %d papers", len(all_papers))
    except Exception as exc:
        logger.warning("Rule-based scoring failed: %s", exc)
    timings["relevance_scoring"] = time.time() - t0

    # ── Step 4: Select & download full text (only top papers) ──
    t0 = time.time()
    full_text_stats = {"total_papers": len(all_papers), "attempted": 0, "success": 0}
    try:
        import full_text_reader
        selected_ft, skipped = full_text_reader.select_papers_for_full_text(all_papers)
        full_text_stats["attempted"] = len(selected_ft)
        all_papers = full_text_reader.read_papers(all_papers)
        ft_ok = sum(1 for p in all_papers if p.get("full_text_source") == "pdf")
        full_text_stats["success"] = ft_ok
        logger.info("Full-text: attempted %d, got %d full PDFs", len(selected_ft), ft_ok)
    except Exception as exc:
        logger.warning("Full-text reading failed: %s", exc)
        for p in all_papers:
            p.setdefault("full_text", p.get("abstract", ""))
            p.setdefault("full_text_source", "abstract_only")
    timings["pdf_download"] = time.time() - t0

    # ── Step 5: LLM / rule-based analysis ──
    t0 = time.time()
    try:
        import llm_analysis
        all_papers = llm_analysis.analyze_papers(all_papers)
        logger.info("Analysis complete")
    except Exception as exc:
        logger.warning("LLM analysis failed: %s", exc)
    timings["llm_analysis"] = time.time() - t0

    # ── Step 6: Storage (SQLite + Excel) ──
    try:
        import storage
        if news_items:
            storage.save_news_to_sqlite(news_items)
            storage.save_news_to_excel(news_items)
        if all_papers:
            storage.save_papers_to_sqlite(all_papers)
            storage.save_papers_to_excel(all_papers)
    except Exception as exc:
        logger.warning("Storage failed: %s", exc)

    # ── Step 7: Report generation ──
    t0 = time.time()
    report_success = False
    md_content = ""
    html_content = ""
    try:
        import report_generator
        result = report_generator.save_report(
            news_items=news_items,
            papers=all_papers,
            source_statuses=source_statuses,
            full_text_stats=full_text_stats,
            timings=timings,
            news_status=news_status,
        )
        md_content = result["md_content"]
        html_content = result["html_content"]
        logger.info("Reports generated: %s, %s", result["md"], result["html"])
        report_success = True
    except Exception as exc:
        logger.error("Report generation failed: %s", exc)
    timings["report_generation"] = time.time() - t0

    # ── Step 8: Email (always try even if partial failures) ──
    t0 = time.time()
    email_success = False
    if send_email and html_content:
        try:
            import send_daily_report_email as mailer
            attachments = []
            for pattern in [f"daily_aihot_{date_str}.xlsx", f"daily_cs_papers_{date_str}.xlsx"]:
                p = config.OUTPUT_DIR / pattern
                if p.exists():
                    attachments.append(p)
            email_success = mailer.send_email(
                html_content=html_content,
                md_content=md_content,
                date_str=date_str,
                attachments=attachments,
            )
        except Exception as exc:
            logger.error("Email sending failed: %s", exc)
    elif send_email and not html_content:
        logger.warning("Report content empty — skipping email")
    timings["email_sending"] = time.time() - t0

    # ── Summary ──
    total_time = sum(timings.values())
    logger.info("=" * 60)
    logger.info("Pipeline summary for %s:", today.isoformat())
    logger.info("  AIHOT news:     %d items (%s)", len(news_items), news_status)
    logger.info("  Total papers:   %d", len(all_papers))
    logger.info("  Full-text:      attempted %d, got %d PDFs",
                full_text_stats["attempted"], full_text_stats["success"])
    logger.info("  Report:         %s" if report_success else "  Report:         ❌ Failed")
    ok_sources = sum(1 for s in source_statuses if s.get("status") == "success")
    logger.info("  Sources:        %d/%d succeeded", ok_sources, len(source_statuses))
    logger.info("  Email:          %s", "✅ Sent" if email_success else "⏭️  Skipped" if not send_email else "❌ Failed")
    logger.info("")
    logger.info("  ⏱️  Timings:")
    for step, t in timings.items():
        logger.info("    %-22s: %.1fs", step, t)
    logger.info("    %-22s: %.1fs", "total", total_time)
    logger.info("=" * 60)

    return report_success and (not send_email or email_success)


def main():
    parser = argparse.ArgumentParser(description="Daily AI News & Paper Digest Pipeline")
    parser.add_argument("--date", help="Run for a specific date (YYYY-MM-DD)")
    parser.add_argument("--send-email", action="store_true", help="Send email after generation")
    parser.add_argument("--no-email", action="store_true", help="Skip email sending")
    args = parser.parse_args()

    load_env()

    if args.date:
        config.RUN_DATE = date.fromisoformat(args.date)
    else:
        config.RUN_DATE = date.today()

    date_str = config.RUN_DATE.strftime("%Y%m%d")
    logger = setup_logging(date_str)
    logger.info("Command line: %s", " ".join(sys.argv))

    send_email = args.send_email or (
        not args.no_email and bool(os.getenv("EMAIL_PASSWORD"))
    )

    success = run_pipeline(send_email=send_email)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
