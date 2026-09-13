import json
import sys
import re
from bs4 import BeautifulSoup
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

# 1. Parse Anfin Blog Tables
print("=== PARSING ANFIN BLOG ===")
with open(r"d:\VESTA\scratch\har\anfin\du_lieu_nganh.har", "r", encoding="utf-8", errors="ignore") as f:
    har = json.load(f)

html_content = ""
for entry in har.get("log", {}).get("entries", []):
    url = entry.get("request", {}).get("url", "")
    if "danh-sach-ma-co-phieu-theo-nganh" in url and "resource=blogs" in url:
        text = entry.get("response", {}).get("content", {}).get("text", "")
        if text:
            d = json.loads(text)
            html_content = d["data"][0]["attributes"]["body_content"]
            break

soup = BeautifulSoup(html_content, "html.parser")
h2_tags = soup.find_all(["h2", "h3"])
print(f"Found {len(h2_tags)} section headers in Anfin blog.")

anfin_records = []
current_sector = "Chung"

for elem in soup.find_all(["h2", "h3", "table"]):
    if elem.name in ["h2", "h3"]:
        header_text = elem.get_text(strip=True)
        # Check if header represents an industry
        if any(w in header_text.lower() for w in ["ngành", "cổ phiếu", "nhóm"]):
            current_sector = header_text
    elif elem.name == "table":
        # Parse table rows
        rows = elem.find_all("tr")
        for row in rows:
            cols = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
            if len(cols) >= 2:
                # typically: STT, Mã CK, Tên công ty, Sàn...
                # let's find which column is ticker (3 uppercase letters)
                for col in cols:
                    if re.match(r"^[A-Z0-9]{3}$", col):
                        company_name = cols[cols.index(col) + 1] if cols.index(col) + 1 < len(cols) else ""
                        exchange = cols[cols.index(col) + 2] if cols.index(col) + 2 < len(cols) else ""
                        anfin_records.append({
                            "sector_header": current_sector,
                            "symbol": col,
                            "company_name": company_name,
                            "exchange": exchange,
                            "source": "anfin"
                        })
                        break

df_anfin = pd.DataFrame(anfin_records)
print(f"Total extracted stock mappings from Anfin: {len(df_anfin)}")
print("Sectors found in Anfin:")
print(df_anfin["sector_header"].value_counts().to_string())
print("\nSample records:")
print(df_anfin.head(15).to_string())

# Save to CSV for inspection
df_anfin.to_csv(r"d:\VESTA\scratch\anfin_sectors_parsed.csv", index=False, encoding="utf-8-sig")
print("Saved to d:\\VESTA\\scratch\\anfin_sectors_parsed.csv")
