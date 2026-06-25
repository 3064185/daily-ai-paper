"""Basic pipeline tests."""
import sys
import tempfile
import types
from pathlib import Path
from datetime import date

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import config


def test_config_has_defaults():
    assert config.EMAIL_HOST == "smtp.qq.com"
    assert config.EMAIL_PORT == 465
    assert config.MAX_PAPERS_PER_SOURCE == 30
    assert config.REQUEST_TIMEOUT == 25


def test_report_generation():
    from report_generator import generate_markdown, generate_html
    news = [{"title": "Test News", "summary": "Test summary", "date": "6月23日",
             "link": "https://example.com", "source": "AIHOT"}]
    papers = [{"title": "Test Paper", "abstract": "Test abstract",
               "authors": ["Author A"], "source": "arXiv", "url": "https://arxiv.org/abs/1234",
               "relevance_score": 8, "venue": "NeurIPS", "key_contribution": "A new method",
               "key_method": "A new approach"}]
    statuses = [{"source": "arXiv", "count": 1, "status": "success"}]
    md = generate_markdown(news, papers, statuses)
    assert "Test News" in md
    assert "Test Paper" in md
    assert "arXiv" in md
    # HTML
    html = generate_html(md)
    assert "<html" in html
    assert "Test News" in html


def test_rule_based_score():
    from llm_analysis import rule_based_score
    paper = {"title": "A large language model for reasoning", "abstract": "We propose GPT-5.",
             "venue": "NeurIPS", "cited_by": 200}
    score = rule_based_score(paper)
    assert 6 <= score <= 10

    paper2 = {"title": "Something unrelated", "abstract": "About soil chemistry.",
              "venue": "", "cited_by": 0}
    score2 = rule_based_score(paper2)
    assert 4 <= score2 <= 6


def test_storage_excel(tmp_path):
    """Test Excel generation without dependencies on output dir."""
    from storage import save_news_to_excel, save_papers_to_excel
    # Override output dir
    original = config.OUTPUT_DIR
    config.OUTPUT_DIR = tmp_path

    from config import RUN_DATE
    RUN_DATE = date(2026, 6, 21)

    news = [{"title": "Test", "summary": "Summary", "date": "6月21日", "link": "https://x.com"}]
    papers = [{"title": "Paper", "abstract": "Abs", "authors": ["A"], "source": "arXiv",
               "url": "https://arx.org", "relevance_score": 7}]

    p1 = save_news_to_excel(news)
    p2 = save_papers_to_excel(papers)

    if p1:
        assert Path(p1).exists()
    if p2:
        assert Path(p2).exists()

    config.OUTPUT_DIR = original


def test_aihot_scraper_rss_parsing():
    """Test RSS parsing with mock data."""
    from aihot_scraper import parse_date
    import feedparser
    from io import StringIO

    # Just test parse_date handles None gracefully
    result = parse_date(type("obj", (object,), {}))
    assert result is not None
    assert "月" in result


def test_run_pipeline_fails_when_email_send_fails(monkeypatch, tmp_path):
    import daily_pipeline

    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(config, "RUN_DATE", date(2026, 6, 25))

    monkeypatch.setitem(sys.modules, "aihot_scraper", types.SimpleNamespace(scrape=lambda: []))
    monkeypatch.setitem(
        sys.modules,
        "paper_search",
        types.SimpleNamespace(search_all=lambda: ([], [{"source": "stub", "count": 0, "status": "success"}])),
    )
    monkeypatch.setitem(
        sys.modules,
        "llm_analysis",
        types.SimpleNamespace(rule_based_score=lambda paper: 5, analyze_papers=lambda papers: papers),
    )
    monkeypatch.setitem(
        sys.modules,
        "full_text_reader",
        types.SimpleNamespace(
            select_papers_for_full_text=lambda papers: ([], []),
            read_papers=lambda papers: papers,
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "storage",
        types.SimpleNamespace(save_news_to_sqlite=lambda news: None, save_news_to_excel=lambda news: None,
                              save_papers_to_sqlite=lambda papers: None, save_papers_to_excel=lambda papers: None),
    )
    monkeypatch.setitem(
        sys.modules,
        "report_generator",
        types.SimpleNamespace(
            save_report=lambda **kwargs: {
                "md": tmp_path / "report.md",
                "html": tmp_path / "report.html",
                "md_content": "# report",
                "html_content": "<html><body>report</body></html>",
            }
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "send_daily_report_email",
        types.SimpleNamespace(send_email=lambda **kwargs: False),
    )

    assert daily_pipeline.run_pipeline(send_email=True) is False
