"""
AIHOT news scraper – RSS-first, webpage-detail fallback.
"""
import logging
import re
from datetime import datetime, timezone
from typing import Optional

import feedparser
import httpx

from config import REQUEST_TIMEOUT, USE_SYSTEM_PROXY

logger = logging.getLogger("aihot")

AIHOT_RSS_URL = "https://aihot.wiki/rss"
AIHOT_BASE = "https://aihot.wiki"

MONTHS_ZH = {
    "Jan": "1月", "Feb": "2月", "Mar": "3月", "Apr": "4月",
    "May": "5月", "Jun": "6月", "Jul": "7月", "Aug": "8月",
    "Sep": "9月", "Oct": "10月", "Nov": "11月", "Dec": "12月",
}


def _build_client() -> httpx.Client:
    kwargs = dict(timeout=httpx.Timeout(REQUEST_TIMEOUT), follow_redirects=True)
    if not USE_SYSTEM_PROXY:
        kwargs["proxy"] = None
    return httpx.Client(**kwargs)


def parse_date(rss_entry) -> Optional[str]:
    """Return a short Chinese date string from an RSS entry."""
    dt = None
    for attr in ("published_parsed", "updated_parsed"):
        v = getattr(rss_entry, attr, None)
        if v:
            try:
                from time import mktime
                dt = datetime.fromtimestamp(mktime(v))
            except Exception:
                continue
            break
    if dt is None:
        dt = datetime.now(timezone.utc)
    return f"{dt.month}月{dt.day}日"


def fetch_aihot_rss() -> list[dict]:
    """Fetch AIHOT RSS feed and return a list of news items."""
    logger.info("Fetching AIHOT RSS feed: %s", AIHOT_RSS_URL)
    feed = feedparser.parse(AIHOT_RSS_URL)
    items = []
    for entry in feed.entries[:20]:
        title = entry.get("title", "").strip()
        link = entry.get("link", "").strip()
        summary = entry.get("summary", "") or ""
        # strip HTML tags from summary
        summary = re.sub(r"<[^>]+>", "", summary).strip()
        pub_date = parse_date(entry)
        items.append({
            "title": title,
            "link": link,
            "summary": summary[:500],
            "date": pub_date,
            "source": "AIHOT",
        })
    logger.info("Fetched %d items from AIHOT RSS", len(items))
    return items


def fetch_detail(url: str) -> Optional[str]:
    """Fetch full article detail page."""
    try:
        with _build_client() as client:
            r = client.get(url)
            r.raise_for_status()
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(r.text, "lxml")
            for sel in ("article", ".content", ".post-content", "main"):
                el = soup.select_one(sel)
                if el:
                    text = el.get_text(separator="\n", strip=True)
                    return text[:3000]
            # fallback: body text
            body = soup.find("body")
            if body:
                return body.get_text(separator="\n", strip=True)[:3000]
    except Exception as exc:
        logger.debug("detail fetch failed for %s: %s", url, exc)
    return None


def scrape() -> list[dict]:
    """Main entry – returns a list of news dicts."""
    items = fetch_aihot_rss()
    # Enrich top-3 items with detail
    for item in items[:3]:
        if item["link"] and not item["link"].startswith("javascript"):
            detail = fetch_detail(item["link"])
            if detail:
                item["detail"] = detail
    return items
