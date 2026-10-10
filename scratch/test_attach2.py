import duckdb
import os

con = duckdb.connect('db/vesta_ohlcv.duckdb', read_only=True)
con.execute("ATTACH 'db/vesta_market_index.duckdb' AS market_index (READ_ONLY)")
con.execute("ATTACH 'db/vesta_market_index.duckdb' AS snapshot (READ_ONLY)")
con.execute("ATTACH 'db/vesta_fundamentals.duckdb' AS fundamentals (READ_ONLY)")
con.execute("ATTACH 'db/vesta_events.duckdb' AS events (READ_ONLY)")
con.execute("ATTACH 'db/vesta_news.duckdb' AS news_db (READ_ONLY)")

print('Direct attach query market_index:', con.execute('SELECT COUNT(*) FROM market_index.core.dim_symbol').fetchone())
print('Direct attach query snapshot:', con.execute('SELECT COUNT(*) FROM snapshot.core.dim_symbol').fetchone())
print('Direct attach query fundamentals:', con.execute('SELECT COUNT(*) FROM fundamentals.core.fundamentals').fetchone())
print('Direct attach query events:', con.execute('SELECT COUNT(*) FROM events.core.corporate_events').fetchone())
print('Direct attach query news_db:', con.execute('SELECT COUNT(*) FROM news_db.core.news').fetchone())

# Now test search_path
try:
    con.execute("SET search_path = 'core, market_index.core, fundamentals.core, events.core, news_db.core'")
    print('search_path works!')
except Exception as e:
    print('search path error:', e)

con.close()
