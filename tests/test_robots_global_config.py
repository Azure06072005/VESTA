"""Unit tests for Global Robots Configuration and Daily Crawler Orchestrator.

Tests verify:
1. Valid YAML structure and schema compliance for configs/robots_global.yaml.
2. Exact RFC 9309 robots.txt Crawl-delay compliance (spglobal, tcct, vecom, vov, vla, vneconomy).
3. Correct multi-tier definitions (Tier 1 API, Tier 2 Enhancers, Tier 3 Macro & News).
4. Watermark retrieval and dry-run execution of DailyCrawlerOrchestrator.
"""

from __future__ import annotations

from pathlib import Path
import pytest
import yaml

from src.etl.daily_crawler_orchestrator import DailyCrawlerOrchestrator

CONFIG_PATH = Path(__file__).resolve().parents[1] / "configs" / "robots_global.yaml"


def test_robots_global_yaml_structure() -> None:
    """Kiểm tra tính hợp lệ của cú pháp YAML và các khối cấu hình bắt buộc."""
    assert CONFIG_PATH.exists(), f"Không tìm thấy file: {CONFIG_PATH}"
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    assert "global_settings" in cfg
    assert "tier1_vnstock_api" in cfg
    assert "tier2_enhancers" in cfg
    assert "tier3_sources" in cfg
    assert "daily_pipeline_schedules" in cfg

    # Verify Look-ahead bias guardrails
    lookahead = cfg["global_settings"].get("lookahead_bias_guardrails", {})
    assert lookahead.get("enabled") is True
    assert lookahead.get("bctc_disclosure_lag_days") == 30


def test_robots_txt_crawl_delay_compliance() -> None:
    """Kiểm tra độ trễ cào (crawl-delay) tuân thủ chính xác các file robots.txt."""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    t3 = cfg["tier3_sources"]

    # 1. VnEconomy mandates Crawl-delay: 1
    assert t3["financial_media_portals"]["vneconomy_vn"]["crawl_delay_seconds"] == 1.0

    # 2. VLA (Logistics) mandates Crawl-delay: 3
    assert t3["industry_associations"]["vla"]["crawl_delay_seconds"] == 3.0

    # 3. S&P Global mandates Crawl-delay: 10
    assert t3["world_macro_institutions"]["spglobal"]["crawl_delay_seconds"] == 10.0

    # 4. TCCT (Tạp chí Công Thương) mandates Crawl-delay: 10
    assert t3["financial_media_portals"]["tcct"]["crawl_delay_seconds"] == 10.0

    # 5. VECOM (Thương mại Điện tử) mandates Crawl-delay: 10
    assert t3["industry_associations"]["vecom"]["crawl_delay_seconds"] == 10.0

    # 6. VOV mandates Crawl-delay: 20
    assert t3["financial_media_portals"]["vov"]["crawl_delay_seconds"] == 20.0

    # 7. WSJ is prohibited for automated crawlers
    assert t3["world_macro_institutions"]["wsj_com"]["status"] == "BLOCKED"


def test_tier1_tier2_enhancers_mapping() -> None:
    """Kiểm tra định nghĩa Tier 1 API vnstock và Tier 2 CafeF/Vietstock enhancers."""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    # Tier 1 modules
    t1_mods = cfg["tier1_vnstock_api"]["modules"]
    assert "dim_symbol" in t1_mods
    assert "market_ohlcv" in t1_mods
    assert "fundamentals" in t1_mods
    assert "corporate_events" in t1_mods

    # Tier 2 Enhancers
    t2 = cfg["tier2_enhancers"]
    assert "cafef" in t2
    assert "vietstock" in t2
    assert "balance_sheet_enhancer" in t2["cafef"]["features"]
    assert "equity_research_reports" in t2["vietstock"]["features"]


def test_daily_crawler_orchestrator_dry_run() -> None:
    """Kiểm tra orchestrator đọc watermark thành công và chạy dry-run 100% không lỗi."""
    orchestrator = DailyCrawlerOrchestrator(config_path=str(CONFIG_PATH))
    watermarks = orchestrator.get_watermarks()

    assert "latest_news_published_at" in watermarks
    assert "latest_macro_policy_published_at" in watermarks
    assert "latest_ohlcv_date" in watermarks
    assert "fundamentals_breakdown" in watermarks

    summary = orchestrator.run_daily_pipeline(tier="all", dry_run=True)
    assert summary["total_records"] == 0
    assert "tier1" in summary
    assert "tier2" in summary
    assert "tier3" in summary
