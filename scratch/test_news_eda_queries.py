import duckdb
import sys

sys.stdout.reconfigure(encoding='utf-8')

con = duckdb.connect('db/vesta_news.duckdb', read_only=True)

print("1. Table counts:")
df_tables = con.execute("""
    SELECT 'core.news' as name, count(*) as cnt FROM core.news
    UNION ALL SELECT 'core.v_stock_news', count(*) FROM core.v_stock_news
    UNION ALL SELECT 'core.v_macro_news', count(*) FROM core.v_macro_news
    UNION ALL SELECT 'core.news_resources', count(*) FROM core.news_resources
    UNION ALL SELECT 'core.macro_policy', count(*) FROM core.macro_policy
    UNION ALL SELECT 'core.sector_news_signal', count(*) FROM core.sector_news_signal
""").fetchdf()
print(df_tables)

print("\n2. News type distribution:")
print(con.execute("SELECT news_type, count(*), round(count(*)*100.0/1149304, 2) as pct FROM core.news GROUP BY news_type ORDER BY count(*) DESC").fetchdf())

print("\n3. Top 10 sources:")
print(con.execute("SELECT source, count(*), round(count(*)*100.0/1149304, 2) as pct FROM core.news GROUP BY source ORDER BY count(*) DESC LIMIT 10").fetchdf())

print("\n4. Year range:")
print(con.execute("""
    SELECT 
        EXTRACT(YEAR FROM published_at) as yr, 
        count(*) as cnt,
        count(CASE WHEN symbol IS NOT NULL THEN 1 END) as stock_cnt,
        count(CASE WHEN symbol IS NULL THEN 1 END) as macro_cnt
    FROM core.news 
    WHERE EXTRACT(YEAR FROM published_at) BETWEEN 2000 AND 2026
    GROUP BY yr 
    ORDER BY yr
""").fetchdf().tail(10))

print("\n5. Day of week & Hour of day:")
print(con.execute("""
    SELECT 
        EXTRACT(DOW FROM published_at) as dow,
        count(*) as cnt
    FROM core.news
    GROUP BY dow ORDER BY dow
""").fetchdf())

print("\n6. Unique symbols in stock news:")
print(con.execute("SELECT count(DISTINCT symbol) as unique_symbols, count(*) as total_stock_news FROM core.v_stock_news").fetchdf())

print("\n7. Top 10 most covered stocks:")
print(con.execute("""
    SELECT symbol, count(*) as cnt 
    FROM core.v_stock_news 
    GROUP BY symbol 
    ORDER BY cnt DESC 
    LIMIT 10
""").fetchdf())

print("\n7b. Top 15 Operating Equities (excluding ETF baskets):")
print(con.execute("""
    SELECT symbol, count(*) as cnt 
    FROM core.v_stock_news 
    WHERE length(symbol) = 3 AND symbol NOT LIKE 'FUE%' AND symbol NOT LIKE 'E1V%'
    GROUP BY symbol 
    ORDER BY cnt DESC 
    LIMIT 15
""").fetchdf())

print("\n8. Headline & Body length stats:")
print(con.execute("""
    SELECT 
        approx_quantile(length(headline), 0.1) as hl_p10,
        approx_quantile(length(headline), 0.5) as hl_p50,
        approx_quantile(length(headline), 0.9) as hl_p90,
        max(length(headline)) as hl_max,
        count(CASE WHEN body IS NOT NULL AND length(body) > 0 THEN 1 END) as body_present,
        count(*) as total_rows
    FROM core.news
""").fetchdf())

con.close()
print("\nAll sample queries passed!")
