import sys
sys.stdout.reconfigure(encoding='utf-8')
import urllib.request
import zipfile
import io
import pandas as pd
from datetime import datetime

# URL của CafeF Index
today = datetime.now().strftime("%d%m%Y")
ymd = datetime.now().strftime("%Y%m%d")

# Thử tải file CafeF Index gần nhất
urls = [
    "http://images1.cafef.vn/data/CafeF.Index.UptoToday.zip",
    f"http://images1.cafef.vn/data/{ymd}/CafeF.Index.Upto{today}.zip",
]

for url in urls:
    try:
        print(f"Testing URL: {url}")
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            content = resp.read()
            z = zipfile.ZipFile(io.BytesIO(content))
            print(f"Zip opened successfully! Files in zip: {z.namelist()}")
            for name in z.namelist()[:5]:
                with z.open(name) as f:
                    df = pd.read_csv(f)
                    print(f"File {name} sample columns:", df.columns.tolist())
                    print("Sample ticker/indices:", df.iloc[:, 0].unique()[:20])
            break
    except Exception as e:
        print(f"Failed {url}: {e}")
