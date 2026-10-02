import duckdb
import pandas as pd

def main():
    print("=== INSPECTING SNAPSHOT DATABASE ===")
    con_snap = duckdb.connect('db/vesta_snapshot.duckdb', read_only=True)
    snap_tables = con_snap.execute("SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema='core' ORDER BY table_name").fetchall()
    for s, t in snap_tables:
        cnt = con_snap.execute(f"SELECT count(*) FROM {s}.{t}").fetchone()[0]
        print(f"  {s}.{t}: {cnt:,} rows")
    
    # Check columns of company_shareholders, dim_symbol_cafef, corporate_officers if available
    for check_tbl in ['company_shareholders', 'dim_symbol_cafef', 'corporate_officers', 'dim_symbol', 'corporate_events']:
        has_tbl = any(t == check_tbl for s, t in snap_tables)
        if has_tbl:
            cols = [r[0] for r in con_snap.execute(f"DESCRIBE core.{check_tbl}").fetchall()]
            print(f"\nColumns for core.{check_tbl}: {cols}")
            sample = con_snap.execute(f"SELECT * FROM core.{check_tbl} LIMIT 3").df()
            print(sample)
    con_snap.close()

    print("\n=== INSPECTING NEWS DATABASE BODY CONTENT ===")
    con_news = duckdb.connect('db/vesta_news.duckdb', read_only=True)
    stats_df = con_news.execute("""
        SELECT 
            source,
            count(*) as total_news,
            count(body) as has_body,
            count(CASE WHEN length(body) > 100 THEN 1 END) as long_body,
            count(symbol) as has_symbol,
            count(CASE WHEN symbol IS NULL OR symbol = '' THEN 1 END) as missing_symbol
        FROM core.news
        GROUP BY source
        ORDER BY total_news DESC
    """).df()
    print(stats_df.to_string())

    # Sample articles with body from tuoitre, tienphong, tinnhanhchungkhoan, cafef
    print("\n=== SAMPLE NEWS WITH BODY ===")
    sample_news = con_news.execute("""
        SELECT source, symbol, headline, length(body) as body_len, substr(body, 1, 300) as body_snippet
        FROM core.news
        WHERE length(body) > 200
        LIMIT 5
    """).df()
    for idx, row in sample_news.iterrows():
        print(f"\n[{row['source']}] (Symbol: {row['symbol']}) - {row['headline']}")
        print(f"Snippet: {row['body_snippet']}...")

    con_news.close()

if __name__ == '__main__':
    main()
