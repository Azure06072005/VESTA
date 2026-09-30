import duckdb

def check():
    con = duckdb.connect('db/vesta_snapshot.duckdb', read_only=True)
    tables = con.execute("SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema IN ('core', 'staging')").fetchall()
    print("Tables in vesta_snapshot:")
    for schema, t in tables:
        print(f" - {schema}.{t}")

    print("\n--- Check core.market_index_daily ---")
    try:
        df = con.execute("""
            SELECT index_code, min(date) as start_date, max(date) as end_date, count(*) as num_rows
            FROM core.market_index_daily
            GROUP BY index_code
            ORDER BY count(*) DESC
        """).fetchdf()
        print(df.to_string())
    except Exception as e:
        print(f"Error querying market_index_daily: {e}")

    print("\n--- Check index constituents & metadata ---")
    try:
        print(con.execute("SELECT * FROM core.dim_index_metadata").fetchdf().to_string())
    except Exception as e:
        print(f"Error metadata: {e}")

    print("\n--- Check intraday index in vesta_intraday_1m.duckdb ---")
    try:
        con_1m = duckdb.connect('db/vesta_intraday_1m.duckdb', read_only=True)
        tables_1m = con_1m.execute("SELECT table_schema, table_name FROM information_schema.tables").fetchall()
        print("1M tables:", tables_1m)
        idx_1m = con_1m.execute("""
            SELECT symbol, min(time) as start_t, max(time) as end_t, count(*) as cnt
            FROM core.market_ohlcv_1m
            WHERE symbol IN ('VNINDEX', 'VN30', 'HNX', 'UPCOM', 'VN100', 'VNDIAMOND', 'VNFINLEAD')
            GROUP BY symbol
        """).fetchdf()
        print("Index in 1M DB:")
        print(idx_1m.to_string() if not idx_1m.empty else "No index symbols in core.market_ohlcv_1m")
    except Exception as e:
        print(f"Error 1m: {e}")

if __name__ == '__main__':
    check()
