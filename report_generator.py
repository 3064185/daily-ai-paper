"""
Generate Markdown and HTML daily reports from papers and news.
"""
import logging
from datetime import date
from pathlib import Path

from config import OUTPUT_DIR

logger = logging.getLogger("report")


def _today() -> date:
    from config import RUN_DATE
    return RUN_DATE or date.today()


def _safe(val) -> str:
    return str(val or "")


def generate_markdown(news_items: list[dict], papers: list[dict],
                      source_statuses: list[dict]) -> str:
    """Generate a Chinese Markdown daily report."""
    today = _today()
    lines = []

    lines.append(f"# AI 前沿与计算机科学论文日报 — {today.isoformat()}")
    lines.append("")
    lines.append(f"> 生成时间：{date.today().isoformat()} · 数据来源：AIHOT + 6 个论文源")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── AI News Section ──
    lines.append("## 🔥 AI 前沿新闻")
    lines.append("")
    if news_items:
        for i, item in enumerate(news_items[:10], 1):
            title = _safe(item.get("title", ""))
            summary = _safe(item.get("summary", ""))
            date_str = _safe(item.get("date", ""))
            link = _safe(item.get("link", ""))
            lines.append(f"### {i}. {title}")
            lines.append("")
            lines.append(f"**日期：** {date_str}")
            lines.append("")
            if summary:
                lines.append(f"{summary}")
                lines.append("")
            if link and link.startswith("http"):
                lines.append(f"[阅读原文]({link})")
                lines.append("")
            detail = item.get("detail", "")
            if detail:
                lines.append(f"> {detail[:500]}")
                lines.append("")
    else:
        lines.append("*今日未获取到 AIHOT 新闻。*")
        lines.append("")

    lines.append("---")
    lines.append("")

    # ── Papers Section ──
    lines.append("## 📄 计算机科学论文推荐")
    lines.append("")

    # Sort by relevance score
    scored = [p for p in papers if p.get("relevance_score", 0) >= 6]
    scored.sort(key=lambda p: p.get("relevance_score", 0), reverse=True)

    if scored:
        lines.append(f"共筛选出 **{len(scored)}** 篇高相关论文：")
        lines.append("")
        for i, paper in enumerate(scored[:10], 1):
            title = _safe(paper.get("title", ""))
            score = paper.get("relevance_score", "-")
            source = _safe(paper.get("source", ""))
            authors = paper.get("authors", [])
            author_str = ", ".join(authors[:3])
            if len(authors) > 3:
                author_str += " et al."
            abstract = _safe(paper.get("abstract", ""))[:300]
            url = _safe(paper.get("url", ""))
            key_contribution = _safe(paper.get("key_contribution", ""))
            key_method = _safe(paper.get("key_method", ""))
            strengths = _safe(paper.get("strengths", ""))
            venue = _safe(paper.get("venue", ""))
            cited_by = paper.get("cited_by", "")

            lines.append(f"### {i}. {title}")
            lines.append("")
            lines.append(f"**相关性评分：** {score}/10  |  **来源：** {source}")
            lines.append("")
            if venue:
                lines.append(f"**发表处：** {venue}")
                lines.append("")
            if authors:
                lines.append(f"**作者：** {author_str}")
                lines.append("")
            if cited_by:
                lines.append(f"**被引：** {cited_by}")
                lines.append("")
            if key_contribution:
                lines.append(f"**核心贡献：** {key_contribution}")
                lines.append("")
            if key_method:
                lines.append(f"**方法：** {key_method}")
                lines.append("")
            if abstract:
                lines.append(f"**摘要：** {abstract}…")
                lines.append("")
            if strengths:
                lines.append(f"**亮点：** {strengths}")
                lines.append("")
            if url and url.startswith("http"):
                lines.append(f"[查看论文]({url})")
                lines.append("")
            lines.append("---")
            lines.append("")
    else:
        lines.append("*今日未筛选出高相关论文。*")
        lines.append("")

    # ── Data Source Status ──
    lines.append("## 📊 数据源状态")
    lines.append("")
    lines.append("| 数据源 | 论文数 | 状态 |")
    lines.append("|--------|--------|------|")
    for s in source_statuses:
        name = _safe(s.get("source", ""))
        count = s.get("count", 0)
        status = _safe(s.get("status", ""))
        status_icon = "✅" if status == "success" else "⚠️" if status == "no_results" else "❌"
        lines.append(f"| {name} | {count} | {status_icon} {status} |")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("*本报告由自动化系统生成。个别数据源失败不影响整体生成。*")

    return "\n".join(lines)


def generate_html(md_content: str) -> str:
    """Convert Markdown to styled HTML."""
    import markdown
    body = markdown.markdown(md_content, extensions=["extra", "tables"])
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI 前沿与计算机科学论文日报</title>
<style>
body {{ font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; line-height: 1.8; color: #333; }}
h1 {{ color: #1a1a2e; border-bottom: 3px solid #e94560; padding-bottom: 10px; }}
h2 {{ color: #16213e; border-bottom: 1px solid #eee; padding-bottom: 5px; }}
h3 {{ color: #0f3460; }}
a {{ color: #e94560; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
blockquote {{ background: #f8f9fa; border-left: 4px solid #e94560; margin: 10px 0; padding: 10px 15px; color: #666; }}
table {{ border-collapse: collapse; width: 100%; margin: 15px 0; }}
th, td {{ border: 1px solid #ddd; padding: 8px 12px; text-align: left; }}
th {{ background: #f5f5f5; }}
code {{ background: #f0f0f0; padding: 2px 5px; border-radius: 3px; }}
hr {{ border: none; border-top: 1px solid #eee; margin: 30px 0; }}
</style>
</head>
<body>
{body}
</body>
</html>"""
    return html


def save_report(news_items: list[dict], papers: list[dict],
                source_statuses: list[dict]) -> dict:
    """Generate and save both MD and HTML reports. Returns paths dict."""
    today = _today()
    date_str = today.strftime("%Y%m%d")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    md = generate_markdown(news_items, papers, source_statuses)
    html = generate_html(md)

    md_path = OUTPUT_DIR / f"daily_combined_report_{date_str}.md"
    html_path = OUTPUT_DIR / f"daily_combined_report_{date_str}.html"

    md_path.write_text(md, encoding="utf-8")
    html_path.write_text(html, encoding="utf-8")

    logger.info("Reports saved: %s, %s", md_path.name, html_path.name)
    return {"md": str(md_path), "html": str(html_path), "md_content": md, "html_content": html}
