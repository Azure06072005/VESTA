import json
import sys
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

with open(r"d:\VESTA\scratch\har\vietstock\du_lieu_nganh.har", "r", encoding="utf-8", errors="ignore") as f:
    har = json.load(f)

for entry in har.get("log", {}).get("entries", []):
    url = entry.get("request", {}).get("url", "")
    content = entry.get("response", {}).get("content", {})
    text = content.get("text", "")
    if "sectionindex" in url and text:
        data = json.loads(text)
        df_sec = pd.DataFrame(data)
        print("=== VIETSTOCK 25 SECTIONS (sectionindex) ===")
        print(df_sec[["SectionID", "Text", "Url", "CloseIndex", "ChangeClose"]].to_string())
        df_sec.to_csv(r"d:\VESTA\scratch\vietstock_25_sections.csv", index=False, encoding="utf-8-sig")
    elif "GetListIndustryGICS" in url and text:
        data = json.loads(text)
        df_gics = pd.DataFrame(data)
        print("\n=== VIETSTOCK GICS LEVEL 1 & 2 ===")
        print(df_gics[df_gics["Level"].isin([1, 2])][["Level", "IndustryCode", "ParentCode", "IndustryName"]].to_string())
        df_gics.to_csv(r"d:\VESTA\scratch\vietstock_gics_all.csv", index=False, encoding="utf-8-sig")
