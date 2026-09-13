import sys
from pathlib import Path
import json
import pandas as pd
import duckdb

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(r"d:\VESTA\src")))

from crawlers.dim_symbol import _authenticate
_authenticate()
import vnstock as vs

# 1. Fetch live vnstock sectors
ref = vs.Reference()
df_vnstock_sec = ref.industry.sectors()
print(f"vnstock sectors: {len(df_vnstock_sec)} stocks, {df_vnstock_sec['industry_name'].nunique()} sectors")

# 2. Load Anfin parsed sectors
df_anfin = pd.read_csv(r"d:\VESTA\scratch\anfin_sectors_parsed.csv")
print(f"Anfin sectors: {len(df_anfin)} stocks, {df_anfin['sector_header'].nunique()} sectors")

# 3. Load Vietstock 25 sections
df_vst_sec = pd.read_csv(r"d:\VESTA\scratch\vietstock_25_sections.csv")
print(f"Vietstock sections: {len(df_vst_sec)} sections")

# 4. Check core.dim_symbol in duckdb
con = duckdb.connect(r"d:\VESTA\db\vesta.duckdb", read_only=True)
df_dim = con.execute("SELECT symbol, organ_name, exchange FROM core.dim_symbol").df()
con.close()
print(f"core.dim_symbol: {len(df_dim)} symbols")

# Merge vnstock sectors with core.dim_symbol
df_merged = df_dim.merge(df_vnstock_sec, on="symbol", how="left")
print(f"Symbols matched with vnstock sectors: {df_merged['industry_name'].notna().sum()} / {len(df_dim)}")

# Let's inspect coverage by exchange
print("\nCoverage by exchange:")
print(df_merged.groupby("exchange")["industry_name"].count())
print("Total per exchange:")
print(df_merged.groupby("exchange")["symbol"].count())

# Let's see top sectors in vnstock
print("\nTop sectors in vnstock:")
print(df_merged["industry_name"].value_counts().to_string())
