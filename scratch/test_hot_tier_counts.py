import duckdb
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def test_counts():
    print("=" * 60)
    print("TESTING HOT TIER ROW COUNTS & RETENTION POLICY")
    print("=" * 60)

    # 1. News
    con_news = duckdb.connect("db/vesta_news.duckdb", read_only=True)
    c_news_hot = con_news.execute("SELECT COUNT(*) FROM core.news WHERE published_at >= '2026-06-01'").fetchone()[0]
    c_news_total = con_news.execute("SELECT COUNT(*) FROM core.news").fetchone()[0]
    print(f"News >= 2026-06-01: {c_news_hot:,} rows / {c_news_total:,} rows (Giảm {100 - (c_news_hot/c_news_total*100):.1f}%)")
    con_news.close()

    # 2. OHLCV
    con_ohlcv = duckdb.connect("db/vesta_ohlcv.duckdb", read_only=True)
    c_1m_hot = con_ohlcv.execute("SELECT COUNT(*) FROM core.market_ohlcv_1m WHERE time >= '2026-09-01'").fetchone()[0]
    c_1m_total = con_ohlcv.execute("SELECT COUNT(*) FROM core.market_ohlcv_1m").fetchone()[0]
    print(f"OHLCV 1m >= 2026-09-01: {c_1m_hot:,} rows / {c_1m_total:,} rows (Giảm {100 - (c_1m_hot/c_1m_total*100):.1f}%)")

    c_d_hot = con_ohlcv.execute("SELECT COUNT(*) FROM core.market_ohlcv_daily WHERE date >= '2024-01-01'").fetchone()[0]
    c_d_total = con_ohlcv.execute("SELECT COUNT(*) FROM core.market_ohlcv_daily").fetchone()[0]
    print(f"OHLCV Daily >= 2024-01-01: {c_d_hot:,} rows / {c_d_total:,} rows (Giảm {100 - (c_d_hot/c_d_total*100):.1f}%)")
    con_ohlcv.close()

    # 3. Market Index Foreign Flow
    con_idx = duckdb.connect("db/vesta_market_index.duckdb", read_only=True)
    c_ff_hot = con_idx.execute("SELECT COUNT(*) FROM core.market_foreign_flow_daily WHERE date >= '2025-01-01'").fetchone()[0]
    c_ff_total = con_idx.execute("SELECT COUNT(*) FROM core.market_foreign_flow_daily").fetchone()[0]
    print(f"Foreign Flow >= 2025-01-01: {c_ff_hot:,} rows / {c_ff_total:,} rows (Giảm {100 - (c_ff_hot/c_ff_total*100):.1f}%)")
    con_idx.close()

    # 4. Fundamentals
    con_fun = duckdb.connect("db/vesta_fundamentals.duckdb", read_only=True)
    c_f_hot = con_fun.execute("SELECT COUNT(*) FROM core.fundamentals WHERE period_end >= '2022-01-01'").fetchone()[0]
    c_f_total = con_fun.execute("SELECT COUNT(*) FROM core.fundamentals").fetchone()[0]
    print(f"Fundamentals >= 2022-01-01: {c_f_hot:,} rows / {c_f_total:,} rows (Giảm {100 - (c_f_hot/c_f_total*100):.1f}%)")

    cols_fn = [c[1] for c in con_fun.execute("PRAGMA table_info('core.financial_notes')").fetchall()]
    print("Financial Notes columns:", cols_fn)
    sample_fn = con_fun.execute("SELECT * FROM core.financial_notes LIMIT 1").fetchone()
    print("Sample row:", sample_fn)
    con_fun.close()

if __name__ == "__main__":
    test_counts()
