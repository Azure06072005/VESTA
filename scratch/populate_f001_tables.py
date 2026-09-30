import duckdb
import sys
import pathlib

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, str(pathlib.Path('src').resolve()))
from crawlers import dim_icb, symbol_exchange_history
from crawlers.db_writer import ResilientDuckDBWriter

# 1. Populate backup DB directly
print(">>> Nạp vào vesta_backup.duckdb...")
con_backup = duckdb.connect("d:/VESTA/db/vesta_backup.duckdb", read_only=False)
try:
    schema_sql = pathlib.Path("configs/duckdb_schema.sql").read_text(encoding="utf-8")
    con_backup.execute(schema_sql)
    cnt_icb = dim_icb.run(con=con_backup)
    cnt_ex = symbol_exchange_history.run(con=con_backup)
    print(f"Hoàn tất vesta_backup.duckdb: ICB={cnt_icb}, Exchange History={cnt_ex}")
finally:
    con_backup.close()

# 2. Populate main DB (vesta_snapshot.duckdb) via ResilientDuckDBWriter
print("\n>>> Nạp vào vesta_snapshot.duckdb (qua ResilientDuckDBWriter)...")
try:
    cnt_icb_main = dim_icb.run(target_db="d:/VESTA/db/vesta_snapshot.duckdb")
    cnt_ex_main = symbol_exchange_history.run(target_db="d:/VESTA/db/vesta_snapshot.duckdb")
    print(f"Hoàn tất vesta_snapshot.duckdb: ICB={cnt_icb_main}, Exchange History={cnt_ex_main}")
except Exception as e:
    print(f"Main DB ghi đệm/báo lỗi: {e}")
