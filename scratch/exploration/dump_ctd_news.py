import duckdb
import os

con = duckdb.connect('d:/VESTA/db/vesta.duckdb', read_only=True)
rows = con.execute("SELECT published_at, headline, source_url FROM core.news WHERE symbol='CTD' ORDER BY published_at DESC").fetchall()

artifact_path = r"C:\Users\ADMIN\.gemini\antigravity-ide\brain\2ebb0c09-579b-48e8-91b8-599a5f512f13\ctd_news_list.md"

with open(artifact_path, "w", encoding="utf-8") as f:
    f.write(f"# CTD (Coteccons) News History\n\n")
    f.write(f"Total articles found: **{len(rows)}**\n\n")
    f.write("| Published Date | Headline | Source URL |\n")
    f.write("| --- | --- | --- |\n")
    for row in rows:
        f.write(f"| {row[0]} | {row[1]} | [Link]({row[2]}) |\n")

print(f"Artifact created with {len(rows)} rows.")
