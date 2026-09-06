"""Unit tests for World Bank macroeconomic crawler."""

from __future__ import annotations

import duckdb
import pytest

from src.crawlers.worldbank_crawler import (
    transform_wb_record,
    WorldBankCrawler,
    WORLDBANK_INDICATORS,
)


def test_transform_wb_record() -> None:
    raw_sample = {
        "indicator": {"id": "NY.GDP.MKTP.KD.ZG", "value": "GDP growth (annual %)"},
        "country": {"id": "VN", "value": "Viet Nam"},
        "countryiso3code": "VNM",
        "date": "2025",
        "value": 8.0188,
        "unit": "",
        "obs_status": "",
        "decimal": 2,
    }
    meta = WORLDBANK_INDICATORS["NY.GDP.MKTP.KD.ZG"]
    rec = transform_wb_record(raw_sample, "NY.GDP.MKTP.KD.ZG", meta)

    assert rec is not None
    assert rec["source"] == "worldbank"
    assert rec["doc_number"] == "NY.GDP.MKTP.KD.ZG"
    assert "8.02%" in rec["headline"] or "8.01%" in rec["headline"]
    assert rec["published_at"].year == 2025
    assert rec["available_at"] == rec["published_at"]
    assert "data.worldbank.org" in rec["source_url"]


def test_transform_wb_record_null_value() -> None:
    raw_sample = {
        "date": "2025",
        "value": None,
    }
    meta = WORLDBANK_INDICATORS["NY.GDP.MKTP.KD.ZG"]
    rec = transform_wb_record(raw_sample, "NY.GDP.MKTP.KD.ZG", meta)
    assert rec is None


def test_worldbank_save_batch(tmp_path) -> None:
    db_file = str(tmp_path / "test_wb.duckdb")
    con = duckdb.connect(db_file)
    con.execute("CREATE SCHEMA core")
    con.execute("""
        CREATE TABLE core.macro_policy (
            source VARCHAR,
            issuing_body VARCHAR,
            doc_type VARCHAR,
            doc_number VARCHAR,
            published_at TIMESTAMP,
            available_at TIMESTAMP,
            headline VARCHAR,
            summary VARCHAR,
            body VARCHAR,
            source_url VARCHAR PRIMARY KEY,
            fetched_at TIMESTAMP
        )
    """)
    con.close()

    crawler = WorldBankCrawler(duckdb_path=db_file)
    meta = WORLDBANK_INDICATORS["NY.GDP.MKTP.KD.ZG"]
    raw = {"date": "2024", "value": 7.09}
    rec = transform_wb_record(raw, "NY.GDP.MKTP.KD.ZG", meta)
    assert rec is not None

    n = crawler.save_batch([rec])
    assert n == 1

    con = duckdb.connect(db_file, read_only=True)
    rows = con.execute("SELECT count(*), max(headline) FROM core.macro_policy WHERE source = 'worldbank'").fetchall()
    con.close()
    assert rows[0][0] == 1
    assert "2024: 7.09%" in rows[0][1]
