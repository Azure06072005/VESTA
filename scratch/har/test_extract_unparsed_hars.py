import json
from pathlib import Path
from bs4 import BeautifulSoup
import re
import sys
import warnings
from bs4 import XMLParsedAsHTMLWarning

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

har_base = Path("scratch/har")

def extract_articles_from_har(source_name: str) -> list[dict]:
    folder = har_base / source_name
    if not folder.exists():
        return []
    
    seen = set()
    records = []
    
    for hf in folder.glob("*.har"):
        try:
            with open(hf, "r", encoding="utf-8", errors="ignore") as f:
                data = json.load(f)
        except Exception:
            continue
            
        for e in data.get("log", {}).get("entries", []):
            req_url = e.get("request", {}).get("url", "")
            resp = e.get("response", {})
            text = resp.get("content", {}).get("text", "")
            if not text or len(text) < 500:
                continue
            
            # Check JSON responses (like infinite scroll APIs)
            mime = resp.get("content", {}).get("mimeType", "")
            if "json" in mime:
                try:
                    js = json.loads(text)
                    items = []
                    if isinstance(js, dict):
                        for k in ["data", "items", "news", "articles", "d"]:
                            if isinstance(js.get(k), list):
                                items = js[k]
                                break
                    elif isinstance(js, list):
                        items = js
                    for it in items:
                        if isinstance(it, dict):
                            t = it.get("title") or it.get("headline") or it.get("Title")
                            u = it.get("url") or it.get("link") or it.get("Url")
                            s = it.get("summary") or it.get("sapo") or it.get("Lead") or t
                            if t and u and u not in seen:
                                seen.add(u)
                                records.append({"source": source_name, "headline": t, "summary": s, "source_url": u})
                except Exception:
                    pass
            
            # Check HTML
            if "html" in mime or len(text) > 2000:
                soup = BeautifulSoup(text, "html.parser")
                for a in soup.find_all("a", href=True):
                    hr = a["href"].strip()
                    t = a.get_text(" ", strip=True)
                    if len(t) < 25 or hr.startswith("javascript") or "#" in hr:
                        continue
                    
                    # check if valid article url
                    full_url = hr
                    if hr.startswith("/"):
                        domain_map = {
                            "nguoiquansat": "https://nguoiquansat.vn",
                            "cafef": "https://cafef.vn",
                            "nhandan": "https://nhandan.vn",
                            "thoibaotaichinh": "https://thoibaotaichinhvietnam.vn",
                            "thoibaonganhang": "https://thoibaonganhang.vn"
                        }
                        full_url = domain_map.get(source_name, "") + hr
                    
                    if full_url in seen or not full_url.startswith("http"):
                        continue
                    
                    # Check url patterns
                    is_article = False
                    if source_name == "nguoiquansat" and ("-d" in hr or ".html" in hr or "/kinh-doanh/" in hr):
                        is_article = True
                    elif source_name == "cafef" and (".chn" in hr or ".htm" in hr):
                        is_article = True
                    elif source_name == "nhandan" and ("-post" in hr or "/kinhte/" in hr or ".html" in hr):
                        is_article = True
                    elif source_name == "thoibaotaichinh" and (".vn/" in full_url and any(k in hr for k in ["tai-chinh", "chung-khoan", "kinh-te"])):
                        is_article = True
                    elif source_name == "thoibaonganhang" and (".html" in hr):
                        is_article = True
                    
                    if is_article:
                        seen.add(full_url)
                        records.append({
                            "source": source_name,
                            "headline": t,
                            "summary": t,
                            "source_url": full_url
                        })
                        
    return records

all_sources = ["nguoiquansat", "cafef", "nhandan", "thoibaotaichinh", "thoibaonganhang"]
total = 0
for src in all_sources:
    recs = extract_articles_from_har(src)
    total += len(recs)
    print(f"[{src.upper()}] Extracted {len(recs):,} articles")
    for r in recs[:2]:
        print(f"   * {r['headline'][:60]} -> {r['source_url'][:60]}")

print(f"\nTotal extractable articles across 5 sources: {total:,}")
