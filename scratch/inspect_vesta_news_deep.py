import duckdb
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

def inspect_news_db():
    con = duckdb.connect('db/vesta_news.duckdb', read_only=True)
    
    # 1. Get all tables and row counts
    tables_query = """
    SELECT table_schema, table_name 
    FROM information_schema.tables 
    WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
    ORDER BY table_schema, table_name
    """
    tables = con.execute(tables_query).fetchall()
    
    report = {}
    print("=== TABLES IN vesta_news.duckdb ===")
    for schema, table in tables:
        count = con.execute(f"SELECT count(*) FROM {schema}.{table}").fetchone()[0]
        cols = con.execute(f"""
            SELECT column_name, data_type, is_nullable 
            FROM information_schema.columns 
            WHERE table_schema = '{schema}' AND table_name = '{table}'
            ORDER BY ordinal_position
        """).fetchall()
        
        print(f"\n[{schema}.{table}] - Total rows: {count:,}")
        col_summary = []
        for col_name, dtype, nullable in cols:
            # Check null count
            null_count = con.execute(f"SELECT count(*) FROM {schema}.{table} WHERE {col_name} IS NULL").fetchone()[0]
            pct_null = (null_count / count * 100) if count > 0 else 0
            col_summary.append({
                "column": col_name,
                "type": dtype,
                "nullable": nullable,
                "null_count": null_count,
                "pct_null": f"{pct_null:.2f}%"
            })
            print(f"  - {col_name:<20} {dtype:<15} (Nulls: {null_count:,} / {pct_null:.1f}%)")
        
        # Sample 2 rows
        if count > 0:
            sample = con.execute(f"SELECT * FROM {schema}.{table} LIMIT 2").fetchdf()
            print("  Sample row 1 keys & values:")
            row1 = sample.iloc[0].to_dict()
            for k, v in row1.items():
                val_str = str(v)
                if len(val_str) > 80:
                    val_str = val_str[:77] + "..."
                print(f"    {k}: {val_str}")
                
        report[f"{schema}.{table}"] = {
            "rows": count,
            "columns": col_summary
        }
    
    con.close()
    
    with open('scratch/vesta_news_schema_audit.json', 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print("\n[OK] Saved audit to scratch/vesta_news_schema_audit.json")

if __name__ == '__main__':
    inspect_news_db()
