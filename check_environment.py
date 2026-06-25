#!/usr/bin/env python3
"""
Environment checker — verifies configuration, network, and dependencies.
Config auto-loads .env on import, so no manual load needed.
"""
import logging
import socket
import sys
from pathlib import Path
import os

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("check")


def check(ok: bool, msg: str):
    icon = "✅" if ok else "❌"
    log.info("%s %s", icon, msg)
    return ok


def status_label(val: str) -> str:
    return "configured" if val else "not configured"


def main():
    ok = True

    log.info("=" * 50)
    log.info("Environment Check")
    log.info("=" * 50)

    # ── Python version ──
    ok &= check(sys.version_info >= (3, 9),
                f"Python version: {sys.version.split()[0]} (need >=3.9)")

    # ── Dependencies ──
    deps = ["httpx", "bs4", "lxml", "openai", "openpyxl",
            "feedparser", "markdown"]
    for dep in deps:
        try:
            __import__(dep.replace("-", "_"))
            ok &= check(True, f"  {dep}: installed")
        except ImportError:
            ok &= check(False, f"  {dep}: MISSING")

    # ── Config (config.py auto-loads .env) ──
    from config import (
        EMAIL_HOST, EMAIL_PORT, EMAIL_USER, EMAIL_PASSWORD, EMAIL_TO,
        OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL, OUTPUT_DIR,
        SENDGRID_API_KEY, SENDGRID_FROM_EMAIL,
    )

    env_path = Path(__file__).parent / ".env"
    in_ci = os.environ.get("GITHUB_ACTIONS") == "true"
    if in_ci:
        log.info("ℹ️ GitHub Actions detected — .env file not required (env vars from workflow env)")
    else:
        ok &= check(env_path.exists(), f".env file: {'found' if env_path.exists() else 'MISSING'}")

    # Determine LLM provider
    llm_provider = "OpenAI"
    if "deepseek" in OPENAI_BASE_URL.lower():
        llm_provider = "DeepSeek"
    elif OPENAI_BASE_URL:
        llm_provider = f"Custom ({OPENAI_BASE_URL})"

    ok &= check(bool(OPENAI_API_KEY), f"LLM provider: {llm_provider}")
    ok &= check(bool(OPENAI_API_KEY), f"  API key: {status_label(OPENAI_API_KEY)}")
    ok &= check(bool(OPENAI_BASE_URL), f"  Base URL: {OPENAI_BASE_URL if OPENAI_BASE_URL else 'not set (using OpenAI default)'}")
    ok &= check(bool(OPENAI_MODEL), f"  Model: {OPENAI_MODEL}")

    if in_ci:
        ok &= check(bool(SENDGRID_API_KEY), f"SENDGRID_API_KEY: {status_label(SENDGRID_API_KEY)}")
        ok &= check(bool(SENDGRID_FROM_EMAIL), f"SENDGRID_FROM_EMAIL: {status_label(SENDGRID_FROM_EMAIL)}")
        ok &= check(bool(EMAIL_TO), f"EMAIL_TO: {status_label(EMAIL_TO)}")
    else:
        ok &= check(bool(EMAIL_HOST), f"EMAIL_HOST: {status_label(EMAIL_HOST)}")
        ok &= check(bool(EMAIL_PORT), f"EMAIL_PORT: {EMAIL_PORT}")
        ok &= check(bool(EMAIL_USER), f"EMAIL_USER: {status_label(EMAIL_USER)}")
        ok &= check(bool(EMAIL_PASSWORD), f"EMAIL_PASSWORD: {status_label(EMAIL_PASSWORD)}")
        ok &= check(bool(EMAIL_TO), f"EMAIL_TO: {status_label(EMAIL_TO)}")
        ok &= check(bool(SENDGRID_API_KEY), f"SENDGRID_API_KEY: {status_label(SENDGRID_API_KEY)}")
        ok &= check(bool(SENDGRID_FROM_EMAIL), f"SENDGRID_FROM_EMAIL: {status_label(SENDGRID_FROM_EMAIL)}")

    # ── Directory writability ──
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    test_file = OUTPUT_DIR / ".check_write"
    try:
        test_file.write_text("ok")
        test_file.unlink()
        ok &= check(True, f"Output dir ({OUTPUT_DIR}): writable")
    except Exception as e:
        ok &= check(False, f"Output dir ({OUTPUT_DIR}): NOT writable ({e})")

    # ── SMTP TCP connectivity (local only; GitHub Actions uses SendGrid only) ──
    if not in_ci:
        try:
            sock = socket.create_connection((EMAIL_HOST, EMAIL_PORT), timeout=10)
            sock.close()
            ok &= check(True, f"SMTP {EMAIL_HOST}:{EMAIL_PORT}: TCP reachable")
        except Exception as e:
            ok &= check(False, f"SMTP {EMAIL_HOST}:{EMAIL_PORT}: UNREACHABLE ({e})")

    # ── Network: AIHOT ──
    try:
        import httpx
        r = httpx.get("https://aihot.wiki/rss", timeout=10, follow_redirects=True)
        ok &= check(r.status_code == 200, f"AIHOT RSS: reachable (HTTP {r.status_code})")
    except Exception as e:
        ok &= check(False, f"AIHOT RSS: UNREACHABLE ({e})")

    # ── Network: arXiv ──
    try:
        r = httpx.get("http://export.arxiv.org/api/query?search_query=cat:cs.AI&start=0&max_results=1", timeout=15)
        ok &= check(r.status_code in (200, 301), f"arXiv API: reachable (HTTP {r.status_code})")
    except Exception as e:
        ok &= check(False, f"arXiv API: UNREACHABLE ({e})")

    log.info("=" * 50)
    log.info("Overall: %s", "ALL CHECKS PASSED 🎉" if ok else "SOME CHECKS FAILED ⚠️")
    log.info("=" * 50)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
