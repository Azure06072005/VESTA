import io
import zipfile
import datetime as dt
import logging
import duckdb
import pandas as pd
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("UpdateOHLCV")

DUCKDB_PATH = "d:/VESTA/db/vesta.duckdb"
CAFEF_BASE_URL = "https://cafef1.mediacdn.vn/data/ami_data"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0.0.0 Safari/537.36"}

DATE_DMY = "11092026"
DATE_YMD = "20260911"

print("=" * 80)
print(f"UPDATING ALL STOCKS & INDICES OHLCV UP TO {DATE_DMY} ({DATE_YMD})")
print("=" * 80)

def parse_ohlcv_csv(content: io.BytesIO, date_cutoff: dt.date) -> pd.DataFrame:
    df = pd.read_csv(content, encoding="utf-8-sig")
    df.columns = [c.replace("<", "").replace(">", "").strip().lower() for c in df.columns]
    
    df["symbol"] = df["ticker"].astype(str).str.strip().str.upper()
    df["date"] = pd.to_datetime(df["dtyyyymmdd"].astype(str), format="%Y%m%d").dt.date
    
    # Filter only new days
    df = df[df["date"] > date_cutoff].copy()
    if df.empty:
        return pd.DataFrame()
        
    df["open"] = pd.to_numeric(df["open"], errors="coerce")
    df["high"] = pd.to_numeric(df["high"], errors="coerce")
    df["low"] = pd.to_numeric(df["low"], errors="coerce")
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype("int64")
    df["fetched_at"] = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    
    clean_df = df[["symbol", "date", "open", "high", "low", "close", "volume", "fetched_at"]]
    clean_df = clean_df.dropna(subset=["symbol", "date"]).drop_duplicates(subset=["symbol", "date"], keep="last")
    return clean_df.reset_index(drop=True)

con = duckdb.connect(DUCKDB_PATH)
cutoff_date = con.execute("SELECT max(date) FROM core.market_ohlcv_daily").fetchone()[0]
logger.info(f"Current max date in core.market_ohlcv_daily: {cutoff_date}")

# 1. UPDATE INDICES
index_url = f"{CAFEF_BASE_URL}/{DATE_YMD}/CafeF.Index.Upto{DATE_DMY}.zip"
logger.info(f"Downloading Indices from {index_url}...")
resp_idx = requests.get(index_url, headers=HEADERS, timeout=60)
resp_idx.raise_for_status()

z_idx = zipfile.ZipFile(io.BytesIO(resp_idx.content))
total_idx = 0
for fname in z_idx.namelist():
    if fname.lower().endswith(".csv"):
        with z_idx.open(fname) as f:
            df_idx = parse_ohlcv_csv(io.BytesIO(f.read()), cutoff_date)
            if not df_idx.empty:
                df_idx = df_idx.rename(columns={"symbol": "index_code"})
                con.register("df_idx_new", df_idx)
                con.execute("""
                    INSERT INTO core.market_index_daily (
                        index_code, date, open, high, low, close, volume, fetched_at
                    )
                    SELECT index_code, date, open, high, low, close, volume, fetched_at
                    FROM df_idx_new
                    ON CONFLICT (index_code, date) DO UPDATE SET
                        open = EXCLUDED.open,
                        high = EXCLUDED.high,
                        low = EXCLUDED.low,
                        close = EXCLUDED.close,
                        volume = EXCLUDED.volume,
                        fetched_at = EXCLUDED.fetched_at
                """)
                total_idx += len(df_idx)
                logger.info(f"  Ingested +{len(df_idx)} new index rows from {fname}")

logger.info(f"Total new index rows ingested: {total_idx:,}")

# 2. UPDATE ALL STOCKS (HSX, HNX, UPCOM)
stock_url = f"{CAFEF_BASE_URL}/{DATE_YMD}/CafeF.SolieuGD.Upto{DATE_DMY}.zip"
logger.info(f"Downloading Stocks OHLCV from {stock_url}...")
resp_stock = requests.get(stock_url, headers=HEADERS, timeout=120)
resp_stock.raise_for_status()

z_stock = zipfile.ZipFile(io.BytesIO(resp_stock.content))
total_stock = 0
for fname in z_stock.namelist():
    if fname.lower().endswith(".csv"):
        with z_stock.open(fname) as f:
            df_stock = parse_ohlcv_csv(io.BytesIO(f.read()), cutoff_date)
            if not df_stock.empty:
                con.register("df_stock_new", df_stock)
                con.execute("""
                    INSERT INTO core.market_ohlcv_daily (
                        symbol, date, open, high, low, close, volume, fetched_at
                    )
                    SELECT symbol, date, open, high, low, close, volume, fetched_at
                    FROM df_stock_new
                    ON CONFLICT (symbol, date) DO UPDATE SET
                        open = EXCLUDED.open,
                        high = EXCLUDED.high,
                        low = EXCLUDED.low,
                        close = EXCLUDED.close,
                        volume = EXCLUDED.volume,
                        fetched_at = EXCLUDED.fetched_at
                """)
                total_stock += len(df_stock)
                logger.info(f"  Ingested +{len(df_stock):,} new stock bars from {fname}")

logger.info(f"Total new stock bars ingested: {total_stock:,}")

# Final verification
new_max_stock, total_stock_rows = con.execute("SELECT max(date), count(*) FROM core.market_ohlcv_daily").fetchone()
new_max_idx, total_idx_rows = con.execute("SELECT max(date), count(*) FROM core.market_index_daily").fetchone()

print("\n" + "=" * 80)
print("UPDATE COMPLETED SUCCESSFULLY:")
print(f"  core.market_ohlcv_daily: {total_stock_rows:,} rows | Max date: {new_max_stock}")
print(f"  core.market_index_daily: {total_idx_rows:,} rows | Max date: {new_max_idx}")
print("=" * 80)

con.close()
