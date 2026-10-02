import duckdb
import sys

sys.stdout.reconfigure(encoding='utf-8')
con = duckdb.connect("db/vesta_snapshot.duckdb", read_only=True)

print("=== KIỂM TRA LỊCH SỬ core.fundamentals THEO TỪNG REPORT TYPE ===")
df_rep = con.execute("""
    SELECT report_type, count(*) as total_rows, min(period_end) as min_date, max(period_end) as max_date, count(DISTINCT symbol) as symbols
    FROM core.fundamentals
    GROUP BY report_type
    ORDER BY report_type
""").df()
print(df_rep)

print("\n=== KIỂM TRA LỊCH SỬ preprocessed.fundamentals_ratios ===")
try:
    df_pre = con.execute("""
        SELECT count(*) as total_rows, min(period_end) as min_date, max(period_end) as max_date, count(DISTINCT symbol) as symbols
        FROM preprocessed.fundamentals_ratios
    """).df()
    print(df_pre)
except Exception as e:
    print(e)

print("\n=== KIỂM TRA LỊCH SỬ core.index_valuation_series ===")
df_val = con.execute("""
    SELECT count(*) as total_rows, min(report_date) as min_date, max(report_date) as max_date, count(DISTINCT index_code) as indices
    FROM core.index_valuation_series
""").df()
print(df_val)

con.close()
