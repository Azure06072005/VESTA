import json
import sys
from pathlib import Path
from bs4 import BeautifulSoup
import re
import datetime as dt

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def extract_tienphong_articles(har_dir):
    articles = []
    seen = set()
    for h in har_dir.glob("*.har"):
        with open(h, "r", encoding="utf-8", errors="ignore") as f:
            data = json.load(f)
        for e in data.get("log", {}).get("entries", []):
            url = e.get("request", {}).get("url", "")
            resp = e.get("response", {}).get("content", {}).get("text", "")
            if not resp:
                continue
            # 1. API morenews
            if "api.tienphong.vn" in url and "morenews" in url:
                try:
                    js = json.loads(resp)
                    html_chunk = js.get("data", {}).get("html", "") if isinstance(js.get("data"), dict) else ""
                    if not html_chunk and isinstance(js.get("data"), str):
                        html_chunk = js.get("data")
                    if html_chunk:
                        soup = BeautifulSoup(html_chunk, "html.parser")
                        for a in soup.find_all("a"):
                            t = a.get_text(strip=True)
                            hr = a.get("href", "")
                            if len(t) > 25 and hr and hr.endswith(".tpo"):
                                full_url = f"https://tienphong.vn{hr}" if hr.startswith("/") else hr
                                if full_url not in seen:
                                    seen.add(full_url)
                                    articles.append({
                                        "source": "tienphong",
                                        "issuing_body": "Báo Tiền Phong",
                                        "headline": t,
                                        "url": full_url,
                                        "file": h.name
                                    })
                except Exception:
                    pass
            # 2. Rendered HTML
            elif "tienphong.vn" in url and ("html" in e.get("response", {}).get("content", {}).get("mimeType", "")):
                soup = BeautifulSoup(resp, "html.parser")
                for a in soup.find_all("a"):
                    t = a.get_text(strip=True)
                    hr = a.get("href", "")
                    if len(t) > 25 and hr and hr.endswith(".tpo"):
                        full_url = f"https://tienphong.vn{hr}" if hr.startswith("/") else hr
                        if full_url not in seen:
                            seen.add(full_url)
                            articles.append({
                                "source": "tienphong",
                                "issuing_body": "Báo Tiền Phong",
                                "headline": t,
                                "url": full_url,
                                "file": h.name
                            })
    return articles

def extract_tuoitre_articles(har_dir):
    articles = []
    seen = set()
    for h in har_dir.glob("*.har"):
        with open(h, "r", encoding="utf-8", errors="ignore") as f:
            data = json.load(f)
        for e in data.get("log", {}).get("entries", []):
            url = e.get("request", {}).get("url", "")
            resp = e.get("response", {}).get("content", {}).get("text", "")
            if not resp:
                continue
            if "tuoitre.vn" in url:
                soup = BeautifulSoup(resp, "html.parser")
                for a in soup.find_all("a"):
                    t = a.get_text(strip=True)
                    hr = a.get("href", "")
                    if len(t) > 25 and hr and hr.endswith(".htm") and not "/video/" in hr:
                        full_url = f"https://tuoitre.vn{hr}" if hr.startswith("/") else hr
                        if full_url not in seen:
                            seen.add(full_url)
                            articles.append({
                                "source": "tuoitre",
                                "issuing_body": "Báo Tuổi Trẻ",
                                "headline": t,
                                "url": full_url,
                                "file": h.name
                            })
    return articles

def extract_vneconomy_articles(har_dir):
    articles = []
    seen = set()
    for h in har_dir.glob("*.har"):
        with open(h, "r", encoding="utf-8", errors="ignore") as f:
            data = json.load(f)
        for e in data.get("log", {}).get("entries", []):
            url = e.get("request", {}).get("url", "")
            resp = e.get("response", {}).get("content", {}).get("text", "")
            if not resp:
                continue
            if "vneconomy.vn" in url:
                soup = BeautifulSoup(resp, "html.parser")
                for a in soup.find_all("a"):
                    t = a.get_text(strip=True)
                    hr = a.get("href", "")
                    if len(t) > 25 and hr and hr.endswith(".htm"):
                        full_url = f"https://vneconomy.vn{hr}" if hr.startswith("/") else hr
                        if full_url not in seen:
                            seen.add(full_url)
                            articles.append({
                                "source": "vneconomy",
                                "issuing_body": "Tạp chí Kinh tế Việt Nam (VnEconomy)",
                                "headline": t,
                                "url": full_url,
                                "file": h.name
                            })
    return articles

def extract_vietstock_articles(har_dir):
    articles = []
    seen = set()
    for h in har_dir.glob("*.har"):
        with open(h, "r", encoding="utf-8", errors="ignore") as f:
            data = json.load(f)
        for e in data.get("log", {}).get("entries", []):
            url = e.get("request", {}).get("url", "")
            resp = e.get("response", {}).get("content", {}).get("text", "")
            if not resp:
                continue
            if "vietstock.vn" in url:
                soup = BeautifulSoup(resp, "html.parser")
                for a in soup.find_all("a"):
                    t = a.get_text(strip=True)
                    hr = a.get("href", "")
                    if len(t) > 25 and hr and (hr.endswith(".htm") or "/2026/" in hr or "/2025/" in hr):
                        full_url = f"https://vietstock.vn{hr}" if hr.startswith("/") else hr
                        if full_url not in seen:
                            seen.add(full_url)
                            articles.append({
                                "source": "vietstock",
                                "issuing_body": "Vietstock Finance",
                                "headline": t,
                                "url": full_url,
                                "file": h.name
                            })
    return articles

tp = extract_tienphong_articles(Path("scratch/har/tienphong"))
tt = extract_tuoitre_articles(Path("scratch/har/tuoitre"))
vne = extract_vneconomy_articles(Path("scratch/har/vneconomy"))
vs = extract_vietstock_articles(Path("scratch/har/vietstock"))

print(f"Tienphong unique articles extracted: {len(tp)}")
print(f"Tuoitre unique articles extracted:   {len(tt)}")
print(f"VnEconomy unique articles extracted:  {len(vne)}")
print(f"Vietstock unique articles extracted:  {len(vs)}")
print(f"TOTAL UNIQUE HAR ARTICLES (4 portals): {len(tp) + len(tt) + len(vne) + len(vs)}")

print("\n--- SAMPLE TIENPHONG ---")
for r in tp[:3]:
    print(f"[{r['file']}] {r['headline'][:70]} -> {r['url']}")

print("\n--- SAMPLE TUOITRE ---")
for r in tt[:3]:
    print(f"[{r['file']}] {r['headline'][:70]} -> {r['url']}")

print("\n--- SAMPLE VNECONOMY ---")
for r in vne[:3]:
    print(f"[{r['file']}] {r['headline'][:70]} -> {r['url']}")

print("\n--- SAMPLE VIETSTOCK ---")
for r in vs[:3]:
    print(f"[{r['file']}] {r['headline'][:70]} -> {r['url']}")
