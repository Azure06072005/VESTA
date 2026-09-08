import zipfile
import io
import requests
import pandas as pd

url = 'https://cafef1.mediacdn.vn/data/ami_data/20260904/CafeF.SolieuGD.Upto04092026.zip'
print("Downloading CafeF.SolieuGD.Upto04092026.zip...")
r = requests.get(url, stream=True, timeout=60)
z = zipfile.ZipFile(io.BytesIO(r.content))

for fn in z.namelist():
    with z.open(fn) as f:
        col_name = '<DTYYYYMMDD>'
        df = pd.read_csv(f, usecols=[col_name])
        min_d = df[col_name].min()
        max_d = df[col_name].max()
        print(f"{fn}: Total rows = {len(df):,}, Min Date = {min_d}, Max Date = {max_d}")

# Also check CafeF.Index.Upto04092026.zip
url_idx = 'https://cafef1.mediacdn.vn/data/ami_data/20260904/CafeF.Index.Upto04092026.zip'
print("\nDownloading CafeF.Index.Upto04092026.zip...")
r_idx = requests.get(url_idx, stream=True, timeout=60)
z_idx = zipfile.ZipFile(io.BytesIO(r_idx.content))
for fn in z_idx.namelist():
    with z_idx.open(fn) as f:
        col_name = '<DTYYYYMMDD>'
        df = pd.read_csv(f, usecols=[col_name])
        min_d = df[col_name].min()
        max_d = df[col_name].max()
        print(f"{fn}: Total rows = {len(df):,}, Min Date = {min_d}, Max Date = {max_d}")
