import json
from pathlib import Path
from bs4 import BeautifulSoup
import re

targets = ["nguoiquansat", "cafef", "nhandan", "thoibaotaichinh", "thoibaonganhang"]

for src in targets:
    har_dir = Path("scratch/har") / src
    if not har_dir.exists():
        print(f"Directory not found: {har_dir}")
        continue
    files = list(har_dir.glob("*.har"))
    print(f"\n--- {src.upper()} ({len(files)} files) ---")
    total_entries = 0
    article_samples = []
    
    for h in files:
        with open(h, "r", encoding="utf-8", errors="ignore") as f:
            try:
                data = json.load(f)
            except Exception as e:
                continue
        entries = data.get("log", {}).get("entries", [])
        total_entries += len(entries)
        
        for e in entries:
            req_url = e.get("request", {}).get("url", "")
            resp_content = e.get("response", {}).get("content", {})
            text = resp_content.get("text", "")
            mime = resp_content.get("mimeType", "")
            
            if "html" in mime and len(text) > 1000:
                soup = BeautifulSoup(text, "html.parser")
                # check if this is an article detail page
                title_el = soup.select_one("h1, .article-title, .title-detail, .title-news")
                body_el = soup.select_one(".article-body, .detail-content, .content, #content, .fck_detail")
                if title_el and body_el and len(body_el.get_text(strip=True)) > 100:
                    title = title_el.get_text(strip=True)
                    body = body_el.get_text(separator="\n", strip=True)
                    article_samples.append((req_url, title, len(body)))
            elif "json" in mime and len(text) > 200:
                try:
                    js = json.loads(text)
                    # Check if json contains article items
                    if isinstance(js, dict) and any(k in js for k in ["data", "items", "news", "articles"]):
                        items = js.get("data") or js.get("items") or js.get("news") or js.get("articles")
                        if isinstance(items, list) and len(items) > 0 and isinstance(items[0], dict):
                            for it in items[:3]:
                                t = it.get("title") or it.get("headline") or it.get("name")
                                u = it.get("url") or it.get("link") or req_url
                                if t:
                                    article_samples.append((u, t, len(str(it))))
                except Exception:
                    pass

    print(f"Total HAR entries: {total_entries}")
    print(f"Found {len(article_samples)} extractable article entries")
    for u, t, blen in article_samples[:3]:
        print(f"  Sample: [{t[:60]}] ({blen} chars) -> {u[:60]}")
