import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import duckdb
from pipeline.sentiment_lexicon import score_headline

con = duckdb.connect('db/vesta_snapshot.duckdb', read_only=True)
query = """
    SELECT 
        p.symbol,
        CAST(p.published_at AS DATE) as pub_date,
        p.headline,
        p.price_at_publish,
        p.price_t5,
        p.price_t30,
        b.above_ma50_pct,
        b.above_ma200_pct,
        ((p.price_t30 - p.price_at_publish) / p.price_at_publish) - 
        ((p.price_t5 - p.price_at_publish) / p.price_at_publish) AS return_diff
    FROM core.pit_events p
    JOIN core.market_breadth_series b ON CAST(p.published_at AS DATE) = b.trade_date
    WHERE p.price_at_publish > 0 AND p.price_t5 > 0 AND p.price_t30 > 0
      AND b.exchange = 'HOSE'
"""
df = con.execute(query).df()
df['is_negative'] = df['headline'].apply(lambda h: score_headline(h or '') < 0.0)
df_neg = df[df['is_negative']].copy()

print(f"Total negative events with HOSE breadth: {len(df_neg)}")

healthy = df_neg[df_neg['above_ma50_pct'] >= 0.45]
crisis = df_neg[df_neg['above_ma50_pct'] < 0.30]
choppy = df_neg[(df_neg['above_ma50_pct'] >= 0.30) & (df_neg['above_ma50_pct'] < 0.45)]

print(f"HEALTHY GATE (>=45%): n={len(healthy)}, Mean={healthy['return_diff'].mean():.2%}, Med={healthy['return_diff'].median():.2%}, Win={(healthy['return_diff']>0).mean():.1%}")
print(f"CRISIS GATE (<30%):   n={len(crisis)}, Mean={crisis['return_diff'].mean():.2%}, Med={crisis['return_diff'].median():.2%}, Win={(crisis['return_diff']>0).mean():.1%}")
print(f"CHOPPY GATE (30-45%): n={len(choppy)}, Mean={choppy['return_diff'].mean():.2%}, Med={choppy['return_diff'].median():.2%}, Win={(choppy['return_diff']>0).mean():.1%}")
con.close()
