import duckdb
import re
from typing import List, Set

SNAPSHOT_DB = "db/vesta_snapshot.duckdb"

# Cache of all valid tickers from dim_symbol + special tickers
VALID_TICKERS: Set[str] = set()

def load_valid_tickers() -> Set[str]:
    global VALID_TICKERS
    if VALID_TICKERS:
        return VALID_TICKERS
    try:
        with duckdb.connect(SNAPSHOT_DB, read_only=True) as con:
            rows = con.execute("SELECT symbol FROM core.dim_symbol").fetchall()
            VALID_TICKERS = {r[0].upper() for r in rows if r[0]}
    except Exception:
        VALID_TICKERS = {"VIC", "VHM", "VRE", "FPT", "VCB", "HPG", "TCB", "MBB", "ACB", "STB", "VPB", "SSI", "VNM", "MWG", "DGC", "GAS", "PLX", "POW", "SAB", "VJC", "BID", "CTG"}
    
    # Add indices and special assets
    VALID_TICKERS.update({"VN30F1M", "VNINDEX", "VN30", "HNX-INDEX", "E1VFVN30", "FUEVFVND", "FUESSVFL", "GB05F", "CFPT2301", "CHPG2301"})
    return VALID_TICKERS

# Common Vietnamese words that happen to match 3-letter combinations
VIETNAMESE_STOPWORDS = {
    'TIN', 'VE', 'THONG', 'THE', 'NAO', 'BAN', 'MUA', 'GIA', 'CO', 'DUNG', 'TIEN', 'VND', 
    'BOT', 'SLM', 'COT', 'RAG', 'AI', 'ARENA', 'ETF', 'BIEU', 'DO', 'NGAY', 'NAM', 'THANG',
    'CHI', 'TIET', 'DANH', 'MUC', 'KE', 'HOACH', 'DAU', 'TU', 'XEM', 'TIM', 'VOI', 'CHO', 
    'HAY', 'TOI', 'CUA', 'CAC', 'MOT', 'HAI', 'BA', 'BON', 'NAM', 'SAU', 'LAN', 'NEN', 'GI'
}

def extract_symbols_from_query(query: str) -> List[str]:
    valid = load_valid_tickers()
    # Normalize Vietnamese tones for tokenization
    tokens = re.findall(r'\b[A-Za-z0-9]{3,8}\b', query.upper())
    
    # Priority 1: Tokens in valid tickers and NOT in vietnamese stopwords
    p1 = [t for t in tokens if t in valid and t not in VIETNAMESE_STOPWORDS]
    if p1:
        return p1
        
    # Priority 2: Tokens in valid tickers
    p2 = [t for t in tokens if t in valid]
    return p2

print("Tokens from 'Hãy cho tôi thông tin về VIC':", extract_symbols_from_query("Hãy cho tôi thông tin về VIC"))
print("Tokens from 'Phân tích mã FPT':", extract_symbols_from_query("Phân tích mã FPT"))
print("Tokens from 'Có nên mua E1VFVN30 không?':", extract_symbols_from_query("Có nên mua E1VFVN30 không?"))
print("Tokens from 'Hãy cho tôi kế hoạch đầu tư':", extract_symbols_from_query("Hãy cho tôi kế hoạch đầu tư"))
