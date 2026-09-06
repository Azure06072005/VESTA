import sys
import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# World Bank API for Vietnam
indicators = [
    ("NY.GDP.MKTP.KD.ZG", "GDP growth (annual %)"),
    ("FP.CPI.TOTL.ZG", "Inflation, consumer prices (annual %)"),
    ("BX.KLT.DINV.WD.GD.ZS", "Foreign direct investment, net inflows (% of GDP)"),
    ("NE.EXP.GNFS.ZS", "Exports of goods and services (% of GDP)"),
]

for ind_code, name in indicators:
    url = f"https://api.worldbank.org/v2/country/VNM/indicator/{ind_code}?format=json&per_page=10"
    r = requests.get(url, timeout=10)
    data = r.json()
    if len(data) > 1 and data[1]:
        latest = data[1][0]
        print(f"[{ind_code}] {name}: Year {latest.get('date')} = {latest.get('value')}")
