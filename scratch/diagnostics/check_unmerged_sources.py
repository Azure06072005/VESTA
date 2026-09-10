import duckdb

con_main = duckdb.connect("d:/VESTA/db/vesta_latest_backup.duckdb", read_only=True)
con_crawl = duckdb.connect("d:/VESTA/db/crawlers_staging.duckdb", read_only=True)
con_stage = duckdb.connect("d:/VESTA/db/vesta_staging.duckdb", read_only=True)

print("Checking crawlers_staging vs vesta_latest_backup:")
main_urls = set(r[0] for r in con_main.execute("SELECT source_url FROM core.macro_policy").fetchall())

crawl_urls = set(r[0] for r in con_crawl.execute("SELECT source_url FROM core.macro_policy").fetchall())
crawl_staging_urls = set(r[0] for r in con_crawl.execute("SELECT source_url FROM staging.macro_policy").fetchall())
all_crawl_urls = crawl_urls | crawl_staging_urls

diff_crawl = all_crawl_urls - main_urls
print(f"crawlers_staging macro_policy URLs not in vesta_latest_backup: {len(diff_crawl)}")

# Check research reports
main_reports = set(r[0] for r in con_main.execute("SELECT report_url FROM core.stock_research_reports").fetchall())
stage_reports = set(r[0] for r in con_stage.execute("SELECT report_url FROM core.stock_research_reports").fetchall())
print(f"Total reports in main: {len(main_reports)}, in vesta_staging: {len(stage_reports)}")
print(f"Reports in vesta_staging not in main: {len(stage_reports - main_reports)}")

# Check news in crawlers_staging if any
con_crawl_tables = [r[0] for r in con_crawl.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='core'").fetchall()]
print(f"Tables in crawlers_staging: {con_crawl_tables}")

con_main.close()
con_crawl.close()
con_stage.close()
