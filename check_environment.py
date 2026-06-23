#!/usr/bin/env python3
"""
Environment checker — verifies configuration, network, and dependencies.
"""
import logging
import os
import socket
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("check")


def check(ok: bool, msg: str):
    icon = "✅" if ok else "❌"
    log.info("%s %s", icon, msg)
    return ok


def main():
    ok = True

    log.info("=" * 50)
    log.info("Environment Check")
    log.info("=" * 50)

    # ── Python version ──
    ok &= check(sys.version_info >= (3, 9),
                f"Python version: {sys.version.split()[0]} (need >=3.9)")

    # ── Dependencies ──
    deps = ["httpx", "beautifulsoup4", "lxml", "openai", "openpyxl",
            "feedparser", "markdown"]
    for dep in deps:
        try:
            __import__(dep.replace("-", "_"))
            ok &= check(True, f"  {dep}: installed")
        except ImportError:
            ok &= check(False, f"  {dep}: MISSING")

    # ── Config ──
    from config import (
        EMAIL_HOST, EMAIL_PORT, EMAIL_USER, EMAIL_PASSWORD, EMAIL_TO,
        OPENAI_API_KEY, OUTPUT_DIR,
    )
    env_path = Path(__file__).parent / ".env"
    ok &= check(env_path.exists(), f".env file: {'found' if env_path.exists() else 'MISSING'}")
    ok &= check(bool(EMAIL_HOST), f"EMAIL_HOST: {EMAIL_HOST or 'NOT SET'}")
    ok &= check(bool(EMAIL_USER), f"EMAIL_USER: {EMAIL_USER or 'NOT SET'}")
    ok &= check(bool(EMAIL_PASSWORD), f"EMAIL_PASSWORD: {'***set***' if EMAIL_PASSWORD else 'NOT SET'}")
    ok &= check(bool(EMAIL_TO), f"EMAIL_TO: {EMAIL_TO or 'NOT SET'}")
    ok &= check(bool(OPENAI_API_KEY) or True,  # optional
                f"OPENAI_API_KEY: {'***set***' if OPENAI_API_KEY else 'not set (optional, rule-based fallback will be used)'}")

    # ── Directory writability ──
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    test_file = OUTPUT_DIR / ".check_write"
    try:
        test_file.write_text("ok")
        test_file.unlink()
        ok &= check(True, f"Output dir ({OUTPUT_DIR}): writable")
    except Exception as e:
        ok &= check(False, f"Output dir ({OUTPUT_DIR}): NOT writable ({e})")

    # ── SMTP TCP connectivity ──
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
        ok &= check(r.status_code == 200, f"arXiv API: reachable (HTTP {r.status_code})")
    except Exception as e:
        ok &= check(False, f"arXiv API: UNREACHABLE ({e})")

    log.info("=" * 50)
    log.info("Overall: %s", "ALL CHECKS PASSED 🎉" if ok else "SOME CHECKS FAILED ⚠️")
    log.info("=" * 50)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
