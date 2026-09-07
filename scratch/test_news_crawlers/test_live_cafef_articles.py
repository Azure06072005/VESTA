import duckdb
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from crawlers.cafef_article_body import fetch_article_html, parse_article_body

con = duckdb.connect("db/vesta.duckdb", read_only=True)
urls = con.execute("""
    SELECT source_url, headline, symbol FROM core.news 
    WHERE source = 'cafef' AND source_url LIKE 'https://cafef.vn%'
    ORDER BY published_at DESC LIMIT 5
""").fetchall()
con.close()

print("=== Testing parse_article_body on 5 Live CafeF URLs ===\n")
for url, headline, sym in urls:
    print(f"Symbol:   {sym}")
    print(f"Headline: {headline}")
    print(f"URL:      {url}")
    try:
        html = fetch_article_html(url)
        res = parse_article_body(html, url)
        p_count = res["body"].count("\n\n") + 1
        print(f"  -> SUCCESS: Extracted {len(res['body'])} chars ({p_count} paragraphs)")
        print(f"  -> Published at: {res['published_at']}")
        print(f"  -> Preview: {res['body'][:120]}...\n")
    except Exception as e:
        print(f"  -> FAILED: {e}\n")
