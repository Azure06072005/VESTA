import duckdb
from typing import List, Dict, Any, Optional

SNAPSHOT_DB = "db/vesta_snapshot.duckdb"
OHLCV_DB = "db/vesta_ohlcv.duckdb"

def search_symbols(q: Optional[str] = None, category: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    results = []
    
    # Static multi-asset registry (high priority items)
    special_assets = [
        {"symbol": "VN30F1M", "name": "HĐTL Chỉ số VN30 (Tháng hiện tại)", "exchange": "HNX Phái sinh", "category": "DERIVATIVE", "industry": "Phái sinh Chỉ số"},
        {"symbol": "VNINDEX", "name": "Chỉ số VN-Index (Toàn sàn HOSE)", "exchange": "HOSE", "category": "INDEX", "industry": "Chỉ số Tổng hợp"},
        {"symbol": "VN30", "name": "Chỉ số VN30 (30 CP Vốn hóa lớn nhất)", "exchange": "HOSE", "category": "INDEX", "industry": "Chỉ số Bluechips"},
        {"symbol": "HNX-INDEX", "name": "Chỉ số HNX-Index", "exchange": "HNX", "category": "INDEX", "industry": "Chỉ số Sở HNX"},
        {"symbol": "E1VFVN30", "name": "Quỹ ETF VFMVN30 (Mô phỏng VN30)", "exchange": "HOSE", "category": "ETF", "industry": "Quỹ ETF Chỉ số"},
        {"symbol": "FUEVFVND", "name": "Quỹ ETF DCVFMVN DIAMOND", "exchange": "HOSE", "category": "ETF", "industry": "Quỹ ETF Kim cương"},
        {"symbol": "FUESSVFL", "name": "Quỹ ETF SSIAM VNFIN LEAD", "exchange": "HOSE", "category": "ETF", "industry": "Quỹ ETF Tài chính"},
        {"symbol": "CFPT2301", "name": "Chứng quyền FPT/2301", "exchange": "HOSE", "category": "CW", "industry": "Chứng quyền có bảo đảm"},
        {"symbol": "CHPG2301", "name": "Chứng quyền HPG/2301", "exchange": "HOSE", "category": "CW", "industry": "Chứng quyền có bảo đảm"},
        {"symbol": "GB05F", "name": "HĐTL Trái phiếu Chính phủ kỳ hạn 5 năm", "exchange": "HNX Phái sinh", "category": "BOND", "industry": "Trái phiếu Phái sinh"},
    ]
    
    q_norm = (q or "").strip().upper()
    cat_norm = (category or "").strip().upper()
    
    for item in special_assets:
        if cat_norm and cat_norm != "ALL" and item["category"] != cat_norm:
            continue
        if q_norm:
            if q_norm in item["symbol"] or q_norm in item["name"].upper() or q_norm in item["industry"].upper():
                results.append(item)
        else:
            results.append(item)
            
    # Search dim_symbol in snapshot DB
    try:
        with duckdb.connect(SNAPSHOT_DB, read_only=True) as con:
            sql = """
                SELECT symbol, organ_name, exchange, industry_name
                FROM core.dim_symbol
                WHERE is_delisted = false
            """
            params = []
            if q_norm:
                sql += " AND (symbol LIKE ? OR organ_name ILIKE ? OR industry_name ILIKE ?)"
                like_p = f"%{q_norm}%"
                params.extend([like_p, like_p, like_p])
                
            sql += f" LIMIT {limit}"
            rows = con.execute(sql, params).fetchall()
            
            for r in rows:
                sym = r[0]
                if any(x["symbol"] == sym for x in results):
                    continue
                results.append({
                    "symbol": sym,
                    "name": r[1] or sym,
                    "exchange": r[2] or "HOSE",
                    "category": "EQUITY",
                    "industry": r[3] or "Cổ phiếu niêm yết",
                })
    except Exception as e:
        print("Dim symbol query error:", e)
        
    return results[:limit]

print("Test 1: Search 'FPT':")
for r in search_symbols("FPT", limit=5):
    print(" ", r)

print("\nTest 2: Search 'VN30':")
for r in search_symbols("VN30", limit=5):
    print(" ", r)

print("\nTest 3: Search 'ETF':")
for r in search_symbols("ETF", limit=5):
    print(" ", r)
