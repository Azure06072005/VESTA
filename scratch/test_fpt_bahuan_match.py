import duckdb
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, "src")
from pipeline.news_fundamental_entity_matcher import FundamentalEntityRegistry

con = duckdb.connect("db/vesta_news.duckdb", read_only=True)
row = con.execute("""
    SELECT n.headline, r.body 
    FROM core.news n
    JOIN core.news_resources r ON n.source_url = r.source_url
    WHERE n.headline LIKE '%Ba Huân bắt tay FPT%'
    LIMIT 1;
""").fetchone()

if row:
    headline, body = row[0], row[1]
    print(f"HEADLINE: {headline}")
    print(f"Body length: {len(body)}")
    reg = FundamentalEntityRegistry()
    reg.load_registry()
    matches = reg.match_entities_in_text(headline, body, "test_url")
    print(f"Số lượng thực thể khớp: {len(matches)}")
    for m in matches:
        print(f" -> Ticker: {m.symbol:5s} | {m.entity_type:12s} | {m.entity_name:25s} | Loc: {m.matched_location} | Conf: {m.confidence_score}")
        
    # In đoạn văn bản chứa entity được match
    for m in matches:
        norm_body = body.lower()
        pos = norm_body.find(m.entity_name.lower())
        if pos != -1:
            print(f"\n[Trích đoạn chứa '{m.entity_name}']:\n{body[max(0, pos-80):min(len(body), pos+120)]}")

con.close()
