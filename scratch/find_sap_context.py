import duckdb
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

con = duckdb.connect("db/vesta_news.duckdb", read_only=True)
body = con.execute("SELECT body FROM core.news_resources WHERE source_url LIKE '%baochinhphu%fpt-va-ba-huan%'").fetchone()[0]
con.close()

pattern = re.compile(r"\b(?:cổ phiếu|mã|cp|chứng khoán|doanh nghiệp)\s+([A-Z]{3})\b", re.IGNORECASE)
for m in pattern.finditer(body):
    print("Match:", m.group(0), "Symbol:", m.group(1))
    pos = m.start()
    print("Context:", body[max(0, pos-40):min(len(body), pos+60)])
