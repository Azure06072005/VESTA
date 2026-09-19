import sys
import duckdb
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, "src")
from pipeline.macro_context_detector import analyze_macro_policy_headline

con = duckdb.connect("db/vesta.duckdb", read_only=True)
print("Querying diverse macro_policy records...")

sql = """
SELECT published_at, issuing_body, headline 
FROM core.macro_policy 
WHERE regexp_matches(lower(headline), 'lãi suất|tín phiếu|tỷ giá|đầu tư công|thông tư 02|nghị định 08|trái phiếu')
ORDER BY published_at DESC 
LIMIT 25
"""
df = con.execute(sql).df()
con.close()

print(f"Loaded {len(df)} representative macro policy records.\n")
for i, row in df.iterrows():
    res = analyze_macro_policy_headline(row['headline'])
    pub = str(row['published_at'])[:10] if pd.notnull(row['published_at']) else "N/A"
    print(f"[{pub}] {res.headline[:70]}")
    print(f"   -> Category : {res.dominant_category}")
    print(f"   -> Surface  : {res.surface_sentiment} | Latent: {res.latent_sentiment} | Alpha Impact: {res.macro_alpha_impact:+.2f}")
    if res.inversion_risk_flag:
        print(f"   -> Inversion Flag: {res.inversion_risk_flag}")
    if res.has_contrastive_shift:
        print(f"   -> Contrastive Shift: {res.contrastive_shift_detail}")
    print()
