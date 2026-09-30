import os
import glob
import sys
import duckdb

sys.stdout.reconfigure(encoding='utf-8')

crawler_files = glob.glob('src/crawlers/**/*.py', recursive=True)
test_files = glob.glob('tests/**/*.py', recursive=True)

f05x_map = {
    'F050': ('market_index_daily', 'cafef_data_market.py', 'test_cafef_data_market.py'),
    'F051': ('market_foreign_flow_daily', 'cafef_foreign_flow.py', 'test_cafef_foreign_flow.py'),
    'F052': ('fundamentals (balance sheet gap)', 'cafef_finance_enhancer.py', 'test_cafef_finance_enhancer.py'),
    'F053': ('batch orchestrator', 'batch_equity_enhancer.py', 'test_batch_equity_enhancer.py'),
    'F054': ('stock_research_reports', 'vietstock_finance_enhancer.py', 'test_new_sector_crawlers.py'),
    'F055': ('core.macro_policy (vietstock)', 'vietstock_crawler.py', 'test_new_sector_crawlers.py'),
    'F056': ('worldbank indicators', 'worldbank_crawler.py', 'test_new_sector_crawlers.py'),
    'F057': ('sbv monetary policy', 'sbv_crawler.py', 'test_new_sector_crawlers.py'),
    'F058': ('baochinhphu', 'baochinhphu_crawler.py', 'test_new_sector_crawlers.py'),
    'F059': ('ssc regulation & sanction', 'ssc_crawler.py', 'test_new_sector_crawlers.py'),
    'F060': ('vneconomy', 'vneconomy_crawler.py', 'test_new_sector_crawlers.py'),
    'F061': ('tinnhanhchungkhoan', 'tinnhanhchungkhoan_crawler.py', 'test_new_sector_crawlers.py'),
    'F062': ('baodautu', 'baodautu_crawler.py', 'test_new_sector_crawlers.py'),
    'F063': ('thoibaonganhang', 'thoibaonganhang_crawler.py', 'test_new_sector_crawlers.py'),
    'F064': ('vinaprint (packaging)', 'vinaprint_crawler.py', 'test_new_sector_crawlers.py'),
    'F065': ('vba (beverage)', 'vba_crawler.py', 'test_new_sector_crawlers.py'),
    'F066': ('nda (national data)', 'nda_crawler.py', 'test_new_sector_crawlers.py'),
    'F067': ('hoinongdan (agriculture)', 'hoinongdan_crawler.py', 'test_new_sector_crawlers.py'),
    'F068': ('moit (energy & trade)', 'moit_crawler.py', 'test_new_sector_crawlers.py'),
    'F069': ('vita (tourism)', 'vita_crawler.py', 'test_new_sector_crawlers.py'),
    'F070': ('vasep (seafood)', 'vasep_crawler.py', 'test_new_sector_crawlers.py'),
    'F071': ('horea (real estate)', 'horea_crawler.py', 'test_new_sector_crawlers.py'),
    'F072': ('checkpoint audit & merge', 'consolidate_staging.py', 'test_new_sector_crawlers.py'),
}

print("=========================================================================================")
print(f"{'Feature':8s} | {'Target Entity / Table':32s} | {'Crawler Script':30s} | {'Exists?':8s}")
print("=========================================================================================")

for fid, (desc, crawler_name, test_name) in f05x_map.items():
    found_crawler = [f for f in crawler_files if os.path.basename(f) == crawler_name]
    status_crawler = "YES" if found_crawler else "NO"
    print(f"{fid:8s} | {desc:32s} | {crawler_name:30s} | {status_crawler:8s}")

# Kiểm tra dữ liệu hiện có trong vesta_snapshot.duckdb
print("\n=========================================================================================")
print("KIỂM TRA DỮ LIỆU THỰC TẾ TRONG db/vesta_snapshot.duckdb CHO CÁC BẢNG F05X")
print("=========================================================================================")

con = duckdb.connect('db/vesta_snapshot.duckdb', read_only=True)
tables_to_check = [
    'core.market_index_daily',
    'core.market_foreign_flow_daily',
    'core.fundamentals',
    'core.stock_research_reports',
    'core.macro_policy',
    'core.regulatory_circulars',
    'core.sector_policy_news',
    'core.v_all_news'
]

for tbl in tables_to_check:
    try:
        count = con.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        print(f"Table {tbl:35s}: {count:>12,d} rows")
    except Exception as e:
        print(f"Table {tbl:35s}: KHÔNG TỒN TẠI / LỖI -> {e}")

con.close()
