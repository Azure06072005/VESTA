import duckdb

con = duckdb.connect('d:/VESTA/db/vesta.duckdb', read_only=True)

print("=" * 80)
print("AUDITING TIME FORMATS & DATE ANOMALIES IN VESTA.DUCKDB")
print("=" * 80)

# 1. CORE.NEWS
print("\n[1] CORE.NEWS")
min_n, max_n, count_n = con.execute("SELECT min(published_at), max(published_at), count(*) FROM core.news").fetchone()
print(f"  Total rows: {count_n:,}")
print(f"  Date range: {min_n} -> {max_n}")

future_n = con.execute("SELECT count(*) FROM core.news WHERE published_at > '2026-09-13'").fetchone()[0]
pre2000_n = con.execute("SELECT count(*) FROM core.news WHERE published_at < '2000-01-01'").fetchone()[0]
null_n = con.execute("SELECT count(*) FROM core.news WHERE published_at IS NULL").fetchone()[0]
zero_time_n = con.execute("""
    SELECT count(*) FROM core.news 
    WHERE EXTRACT(HOUR FROM published_at) = 0 
      AND EXTRACT(MINUTE FROM published_at) = 0 
      AND EXTRACT(SECOND FROM published_at) = 0
""").fetchone()[0]

print(f"  Null published_at: {null_n}")
print(f"  Future dates (> 2026-09-13): {future_n}")
print(f"  Pre-2000 dates (< 2000-01-01): {pre2000_n}")
print(f"  Exact 00:00:00 timestamps: {zero_time_n:,} ({zero_time_n/count_n*100:.2f}%)")

# Breakdown by source in core.news
print("\n  core.news breakdown by source:")
for src, cnt, min_d, max_d in con.execute("""
    SELECT source, count(*), min(published_at), max(published_at)
    FROM core.news
    GROUP BY source
    ORDER BY count(*) DESC
""").fetchall():
    print(f"    - {src}: {cnt:,} rows ({min_d} to {max_d})")

# 2. CORE.MACRO_POLICY
print("\n[2] CORE.MACRO_POLICY")
min_m, max_m, count_m = con.execute("SELECT min(published_at), max(published_at), count(*) FROM core.macro_policy").fetchone()
print(f"  Total rows: {count_m:,}")
print(f"  Date range: {min_m} -> {max_m}")

future_m = con.execute("SELECT count(*) FROM core.macro_policy WHERE published_at > '2026-09-13'").fetchone()[0]
pre2000_m = con.execute("SELECT count(*) FROM core.macro_policy WHERE published_at < '2000-01-01'").fetchone()[0]
null_m = con.execute("SELECT count(*) FROM core.macro_policy WHERE published_at IS NULL").fetchone()[0]
zero_time_m = con.execute("""
    SELECT count(*) FROM core.macro_policy 
    WHERE EXTRACT(HOUR FROM published_at) = 0 
      AND EXTRACT(MINUTE FROM published_at) = 0 
      AND EXTRACT(SECOND FROM published_at) = 0
""").fetchone()[0]

print(f"  Null published_at: {null_m}")
print(f"  Future dates (> 2026-09-13): {future_m}")
print(f"  Pre-2000 dates (< 2000-01-01): {pre2000_m}")
print(f"  Exact 00:00:00 timestamps: {zero_time_m:,} ({zero_time_m/count_m*100:.2f}%)")

# Check pinned date 2026-09-05 in macro_policy
p0905 = con.execute("""
    SELECT source, count(*) 
    FROM core.macro_policy 
    WHERE CAST(published_at AS DATE) = '2026-09-05' 
    GROUP BY source 
    ORDER BY count(*) DESC
""").fetchall()
print(f"\n  Rows pinned to 2026-09-05 in core.macro_policy (Clock Banner Bug):")
for s, cnt in p0905:
    print(f"    - {s}: {cnt:,} rows")

con.close()
