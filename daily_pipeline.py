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
    logger.info("=" * 60)
    logger.info("Daily Pipeline starting for %s", today.isoformat())
    logger.info("Send email: %s", send_email)
    logger.info("=" * 60)

    # Ensure output dir
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── Step 1: AIHOT News ──
    news_items = []
    try:
        import aihot_scraper
        news_items = aihot_scraper.scrape()
        logger.info("AIHOT news: %d items", len(news_items))
    except Exception as exc:
        logger.error("AIHOT scraper failed: %s", exc)

    # ── Step 2: Paper search ──
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

    # ── Step 3: Full text reading ──
    try:
        import full_text_reader
        all_papers = full_text_reader.read_papers(all_papers)
    except Exception as exc:
        logger.warning("Full-text reading failed: %s", exc)

    # ── Step 4: LLM / rule-based analysis ──
    try:
        import llm_analysis
        all_papers = llm_analysis.analyze_papers(all_papers)
        logger.info("Analysis complete")
    except Exception as exc:
        logger.warning("LLM analysis failed: %s", exc)

    # ── Step 5: Storage (SQLite + Excel) ──
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

    # ── Step 6: Report generation ──
    report_success = False
    md_content = ""
    html_content = ""
    try:
        import report_generator
        result = report_generator.save_report(news_items, all_papers, source_statuses)
        md_content = result["md_content"]
        html_content = result["html_content"]
        logger.info("Reports generated: %s, %s", result["md"], result["html"])
        report_success = True
    except Exception as exc:
        logger.error("Report generation failed: %s", exc)

    # ── Step 7: Email (optional) ──
    email_success = False
    if send_email and report_success and html_content:
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
    elif send_email and not report_success:
        logger.warning("Report generation failed — skipping email")

    # ── Summary ──
    logger.info("=" * 60)
    logger.info("Pipeline summary for %s:", today.isoformat())
    logger.info("  AIHOT news:     %d items", len(news_items))
    logger.info("  Total papers:   %d", len(all_papers))
    logger.info("  Report:         %s", "✅ Success" if report_success else "❌ Failed")
    logger.info("  Sources:        %d/%d succeeded",
                sum(1 for s in source_statuses if s.get("status") == "success"),
                len(source_statuses))
    logger.info("  Email:          %s", "✅ Sent" if email_success else "⏭️  Skipped" if not send_email else "❌ Failed")
    logger.info("=" * 60)

    return report_success


def main():
    parser = argparse.ArgumentParser(description="Daily AI News & Paper Digest Pipeline")
    parser.add_argument("--date", help="Run for a specific date (YYYY-MM-DD)")
    parser.add_argument("--send-email", action="store_true", help="Send email after generation")
    parser.add_argument("--no-email", action="store_true", help="Skip email sending")
    args = parser.parse_args()

    load_env()

    # Determine run date
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
