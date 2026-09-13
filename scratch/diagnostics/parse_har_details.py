import json
import sys
from pathlib import Path
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

# 1. Inspect Vietstock GetListIndustryGICS
def parse_vietstock():
    print("=== VIETSTOCK INDUSTRY DATA ===")
    har_path = Path(r"d:\VESTA\scratch\har\vietstock\du_lieu_nganh.har")
    with open(har_path, "r", encoding="utf-8", errors="ignore") as f:
        har = json.load(f)
    
    industries = None
    heatmap = None
    for entry in har.get("log", {}).get("entries", []):
        url = entry.get("request", {}).get("url", "")
        text = entry.get("response", {}).get("content", {}).get("text", "")
        if "GetListIndustryGICS" in url and text:
            industries = json.loads(text)
        elif "GetHeatmapGICS" in url and text:
            heatmap = json.loads(text)

    if industries:
        df_ind = pd.DataFrame(industries)
        print(f"Total Vietstock GICS Industries: {len(df_ind)}")
        print(df_ind.head(15).to_string())
        print("\nLevels breakdown:")
        print(df_ind["Level"].value_counts().to_string())
        print("\nLevel 1 Sectors:")
        print(df_ind[df_ind["Level"] == 1][["IndustryCode", "IndustryName"]].to_string())
        print("\nLevel 2 Sectors:")
        print(df_ind[df_ind["Level"] == 2][["IndustryCode", "ParentCode", "IndustryName"]].head(20).to_string())

    if heatmap:
        df_heat = pd.DataFrame(heatmap)
        print(f"\nHeatmap records: {len(df_heat)}")
        print("Heatmap columns:", df_heat.columns.tolist())
        print(df_heat.head(5).to_string())

# 2. Inspect Anfin all-stocks and blog
def parse_anfin():
    print("\n=== ANFIN INDUSTRY DATA ===")
    har_path = Path(r"d:\VESTA\scratch\har\anfin\du_lieu_nganh.har")
    with open(har_path, "r", encoding="utf-8", errors="ignore") as f:
        har = json.load(f)

    all_stocks = None
    blog_content = None
    for entry in har.get("log", {}).get("entries", []):
        url = entry.get("request", {}).get("url", "")
        text = entry.get("response", {}).get("content", {}).get("text", "")
        if "all-stocks" in url and text:
            all_stocks = json.loads(text)
        elif "danh-sach-ma-co-phieu-theo-nganh" in url and "resource=blogs" in url and text:
            blog_content = json.loads(text)

    if all_stocks:
        data = all_stocks.get("data", {})
        stocks = data.get("data", [])
        print(f"Total Anfin stocks: {len(stocks)}")
        if stocks:
            sample = stocks[0]
            print("Sample stock keys:", list(sample.keys()))
            print("Sample stock:", json.dumps(sample, ensure_ascii=False, indent=2))
            df_stk = pd.DataFrame(stocks)
            for col in ["sector", "industry", "category", "sector_name", "industry_name"]:
                if col in df_stk.columns:
                    print(f"Found column '{col}':", df_stk[col].value_counts().head(10).to_string())

    if blog_content:
        data = blog_content.get("data", [])
        if data:
            attrs = data[0].get("attributes", {})
            content = attrs.get("content", "")
            print(f"Blog content length: {len(content)}")
            # print sample
            print("Blog sample:", content[:500])

parse_vietstock()
parse_anfin()
