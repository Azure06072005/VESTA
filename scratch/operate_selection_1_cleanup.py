import duckdb
import os
import sys

# Ensure UTF-8 output on Windows
sys.stdout.reconfigure(encoding='utf-8')

target_db = "db/vesta_snapshot.duckdb"
print(f"=== BAT DAU DON DEP LUA CHON 1 TREN {target_db} ===")

initial_size = os.path.getsize(target_db) / (1024 ** 3)
print(f"Dung luong ban dau: {initial_size:.2f} GB")

con = duckdb.connect(target_db, read_only=False)

drop_targets = [
    # Views
    ("VIEW", "core", "v_market_ohlcv_1m_dual"),
    ("VIEW", "core", "v_market_ohlcv_dual"),
    
    # OHLCV Tables (Da co trong db/vesta_ohlcv.duckdb: 5.18M 1D, 22.75M 1m, 260k index)
    ("TABLE", "core", "market_ohlcv_1m"),
    ("TABLE", "core", "market_ohlcv_daily"),
    ("TABLE", "core", "market_index_daily"),
    ("TABLE", "staging", "market_ohlcv_daily"),
    
    # News & Macro Tables (Da co trong db/vesta_news.duckdb: 1.15M tin hop nhat)
    ("TABLE", "core", "news"),
    ("TABLE", "core", "news_resources"),
    ("TABLE", "staging", "news"),
    ("TABLE", "staging", "news_resources"),
    ("TABLE", "core", "macro_policy"),
    ("TABLE", "staging", "macro_policy"),
    ("TABLE", "preprocessed", "macro_policy"),
]

dropped_count = 0
for obj_type, schema, name in drop_targets:
    try:
        con.execute(f'DROP {obj_type} IF EXISTS "{schema}"."{name}";')
        print(f"  [OK] Da DROP {obj_type}: {schema}.{name}")
        dropped_count += 1
    except Exception as e:
        print(f"  [ERR] Loi khi DROP {schema}.{name}: {e}")

print(f"\nDa hoan thanh DROP {dropped_count} doi tuong.")
print("Dang thuc hien CHECKPOINT...")
con.execute("CHECKPOINT;")

con.close()

final_size = os.path.getsize(target_db) / (1024 ** 3)
print(f"Dung luong sau khi DROP & CHECKPOINT: {final_size:.2f} GB")

con_check = duckdb.connect(target_db, read_only=True)
remaining_tables = con_check.execute("""
    SELECT table_schema, count(*) 
    FROM information_schema.tables 
    WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
    GROUP BY table_schema
    ORDER BY table_schema
""").fetchall()

print("\nThong ke cac bang con lai theo schema:")
for s, c in remaining_tables:
    print(f"  Schema [{s}]: {c} tables/views")

con_check.close()
print("Hoan tat don dep Lua chon 1!")
