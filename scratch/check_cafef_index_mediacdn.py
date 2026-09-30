import sys
sys.stdout.reconfigure(encoding='utf-8')
import requests
import zipfile
import io
import pandas as pd
from datetime import datetime, timedelta

CAFEF_DATA_BASE_URL = "https://cafef1.mediacdn.vn/data/ami_data"
headers = {"User-Agent": "Mozilla/5.0"}

# Tìm file Index gần nhất
now = datetime.now()
found = False
for day_offset in range(10):
    target_date = now - timedelta(days=day_offset)
    dmy = target_date.strftime("%d%m%Y")
    ymd = target_date.strftime("%Y%m%d")
    url = f"{CAFEF_DATA_BASE_URL}/{ymd}/CafeF.Index.Upto{dmy}.zip"
    try:
        r = requests.head(url, headers=headers, timeout=5)
        if r.status_code == 200:
            print(f"Found active Index ZIP URL: {url}")
            r_get = requests.get(url, headers=headers, timeout=30)
            z = zipfile.ZipFile(io.BytesIO(r_get.content))
            print("Files in ZIP:", z.namelist())
            for fname in z.namelist():
                with z.open(fname) as f:
                    df = pd.read_csv(f)
                    print(f"\n--- {fname} ({len(df)} rows) ---")
                    print("Columns:", df.columns.tolist())
                    print("Unique indices in first column:", df.iloc[:, 0].unique().tolist()[:30])
            found = True
            break
    except Exception as e:
        print(f"Error {url}: {e}")

if not found:
    print("Could not find CafeF Index zip on mediacdn.vn")
