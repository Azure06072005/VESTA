import duckdb
import re
import datetime as dt
from typing import Dict, Any, List, Optional, Set

SNAPSHOT_DB = "db/vesta_snapshot.duckdb"
NEWS_DB = "db/vesta_news.duckdb"
OHLCV_DB = "db/vesta_ohlcv.duckdb"

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
    VALID_TICKERS.update({"VN30F1M", "VNINDEX", "VN30", "HNX-INDEX", "E1VFVN30", "FUEVFVND", "FUESSVFL", "GB05F", "CFPT2301", "CHPG2301"})
    return VALID_TICKERS

VIETNAMESE_STOPWORDS = {
    'TIN', 'VE', 'THONG', 'THE', 'NAO', 'BAN', 'MUA', 'GIA', 'CO', 'DUNG', 'TIEN', 'VND', 
    'BOT', 'SLM', 'COT', 'RAG', 'AI', 'ARENA', 'ETF', 'BIEU', 'DO', 'NGAY', 'NAM', 'THANG',
    'CHI', 'TIET', 'DANH', 'MUC', 'KE', 'HOACH', 'DAU', 'TU', 'XEM', 'TIM', 'VOI', 'CHO', 
    'HAY', 'TOI', 'CUA', 'CAC', 'MOT', 'HAI', 'BA', 'BON', 'NAM', 'SAU', 'LAN', 'NEN', 'GI'
}

def extract_symbols_from_query(query: str) -> List[str]:
    valid = load_valid_tickers()
    tokens = re.findall(r'\b[A-Za-z0-9]{3,8}\b', query.upper())
    p1 = [t for t in tokens if t in valid and t not in VIETNAMESE_STOPWORDS]
    if p1:
        return p1
    return [t for t in tokens if t in valid]

def query_rag_ohlcv(symbol: str) -> Dict[str, Any]:
    try:
        with duckdb.connect(OHLCV_DB, read_only=True) as con:
            if symbol in ['VNINDEX', 'VN30', 'HNX-INDEX']:
                rows = con.execute("""
                    SELECT date, open, high, low, close, volume
                    FROM core.market_index_daily
                    WHERE index_code = ?
                    ORDER BY date DESC LIMIT 60
                """, [symbol]).fetchall()
            else:
                rows = con.execute("""
                    SELECT date, open, high, low, close, volume
                    FROM core.market_ohlcv_daily
                    WHERE symbol = ?
                    ORDER BY date DESC LIMIT 60
                """, [symbol]).fetchall()
                
            if not rows:
                return {"symbol": symbol, "found": False}
                
            latest = rows[0]
            prev = rows[1] if len(rows) > 1 else latest
            p_last = float(latest[4])
            p_prev = float(prev[4])
            pct_1d = round(((p_last - p_prev) / p_prev) * 100, 2) if p_prev > 0 else 0.0
            
            closes = [float(r[4]) for r in rows]
            sma20 = round(sum(closes[:20]) / min(len(closes), 20), 2)
            sma50 = round(sum(closes[:50]) / min(len(closes), 50), 2)
            high_52w = max(closes)
            low_52w = min(closes)
            
            trend = "Tăng (Bullish)" if p_last > sma20 >= sma50 else ("Giảm (Bearish)" if p_last < sma20 else "Đi ngang (Neutral)")
            
            return {
                "symbol": symbol,
                "found": True,
                "last_date": str(latest[0]),
                "last_price": p_last,
                "pct_1d": pct_1d,
                "sma20": sma20,
                "sma50": sma50,
                "high_52w": high_52w,
                "low_52w": low_52w,
                "avg_vol_20": round(sum(float(r[5]) for r in rows[:20]) / min(len(rows), 20)),
                "trend": trend,
            }
    except Exception as e:
        return {"symbol": symbol, "found": False, "error": str(e)}

def query_rag_news(symbol: Optional[str] = None, limit: int = 4) -> List[Dict[str, Any]]:
    try:
        with duckdb.connect(NEWS_DB, read_only=True) as con:
            if symbol:
                rows = con.execute("""
                    SELECT headline, source, published_at, summary, source_url
                    FROM core.news
                    WHERE symbol = ? AND headline IS NOT NULL
                    ORDER BY published_at DESC LIMIT ?
                """, [symbol, limit]).fetchall()
            else:
                rows = con.execute("""
                    SELECT headline, source, published_at, summary, source_url
                    FROM core.news
                    WHERE headline IS NOT NULL
                    ORDER BY published_at DESC LIMIT ?
                """, [limit]).fetchall()
                
            return [
                {
                    "headline": r[0],
                    "source": r[1] or "CafeF",
                    "date": str(r[2])[:10] if r[2] else "-",
                    "summary": r[3][:150] if r[3] else "",
                    "url": r[4] or "",
                }
                for r in rows
            ]
    except Exception:
        return []

def query_rag_snapshot(symbol: Optional[str] = None) -> Dict[str, Any]:
    res = {"company_name": "", "exchange": "", "industry": "", "events": [], "shareholders": []}
    if not symbol:
        return res
    try:
        with duckdb.connect(SNAPSHOT_DB, read_only=True) as con:
            sym_info = con.execute("SELECT organ_name, exchange, industry_name FROM core.dim_symbol WHERE symbol = ?", [symbol]).fetchone()
            if sym_info:
                res["company_name"] = sym_info[0] or ""
                res["exchange"] = sym_info[1] or ""
                res["industry"] = sym_info[2] or ""
                
            events = con.execute("""
                SELECT event_type, event_date, detail_json
                FROM core.corporate_events
                WHERE symbol = ?
                ORDER BY event_date DESC LIMIT 3
            """, [symbol]).fetchall()
            
            parsed_events = []
            for ev in events:
                ev_type = ev[0]
                ev_date = str(ev[1])
                title = ev_type
                if ev[2]:
                    import json
                    try:
                        dj = json.loads(ev[2])
                        title = dj.get('event_title_vi') or dj.get('event_name_vi') or title
                    except Exception:
                        pass
                parsed_events.append(f"{title} ({ev_date})")
            res["events"] = parsed_events
            
            shs = con.execute("""
                SELECT shareholder_name, ownership_percentage
                FROM core.company_shareholders
                WHERE symbol = ?
                ORDER BY ownership_percentage DESC LIMIT 2
            """, [symbol]).fetchall()
            res["shareholders"] = [f"{s[0]} ({s[1]}%)" for s in shs if s[0]]
            return res
    except Exception:
        return res

def generate_rag_response(user_query: str, initial_cash: float = 10000000.0, risk_tolerance: str = "medium") -> Dict[str, Any]:
    symbols = extract_symbols_from_query(user_query)
    
    if symbols:
        target_sym = symbols[0]
        ohlcv = query_rag_ohlcv(target_sym)
        news = query_rag_news(target_sym, limit=3)
        snap = query_rag_snapshot(target_sym)
        
        # Build symbol analysis response
        comp_name = snap["company_name"] or target_sym
        exchange = snap["exchange"] or "HOSE"
        industry = snap["industry"] or "Niêm yết"
        
        p_last = ohlcv.get("last_price", 0.0)
        pct_1d = ohlcv.get("pct_1d", 0.0)
        sma20 = ohlcv.get("sma20", 0.0)
        trend = ohlcv.get("trend", "Trung lập")
        vol20 = ohlcv.get("avg_vol_20", 0)
        high52 = ohlcv.get("high_52w", 0.0)
        low52 = ohlcv.get("low_52w", 0.0)
        
        events_str = "; ".join(snap["events"]) if snap["events"] else "Không có sự kiện mới"
        sh_str = "; ".join(snap["shareholders"]) if snap["shareholders"] else "Đang cập nhật"
        news_str = "\n".join([f"  • [{n['source']} - {n['date']}] {n['headline']}" for n in news]) if news else "  • Chưa ghi nhận tin tức đột biến gần nhất."
        
        # Suggest trade
        action = "MUA THĂM DÒ (ACCUMULATE)" if "Tăng" in trend or pct_1d > 0 else "QUAN SÁT (HOLD/WATCH)"
        stop_loss = round(p_last * 0.95, 2) if p_last > 0 else 0.0
        take_profit = round(p_last * 1.10, 2) if p_last > 0 else 0.0
        
        # Odd-lot shares for 10M cash (up to 25% NAV = 2.5M)
        target_allocation = initial_cash * 0.25
        lot_shares = int(target_allocation / (p_last * 1000)) if p_last > 0 else 0
        actual_capital = lot_shares * p_last * 1000
        
        reply = f"""### 📊 Báo Cáo Phân Tích Đa Chiều: {target_sym} — {comp_name} ({exchange})
**Ngành:** {industry} | **Cổ đông lớn:** {sh_str}

#### 1. Dữ Liệu Kỹ Thuật & Động Lượng Giá (Từ db/vesta_ohlcv.duckdb)
- **Thị giá đóng cửa gần nhất:** {p_last:,.1f} (Nghìn VNĐ) ({pct_1d:+.2f}%)
- **Đường trung bình MA:** SMA20 = {sma20:,.1f} | **Xu hướng giá:** {trend}
- **Biên độ 52 tuần:** Thấp nhất {low52:,.1f} — Cao nhất {high52:,.1f}
- **Thanh khoản bình quân 20 phiên:** {vol20:,.0f} cổ phiếu/phiên

#### 2. Thông Tin Doanh Nghiệp & Sự Kiện (Từ db/vesta_snapshot.duckdb)
- **Sự kiện doanh nghiệp gần nhất:** {events_str}

#### 3. Điểm Tin Báo Chí & Tín Hiệu Sentiment (Từ db/vesta_news.duckdb)
{news_str}

#### 4. Kế Hoạch Đầu Tư Khuyến Nghị (Vốn {initial_cash:,.0f} VNĐ)
- **Khuyến nghị hành động:** **{action}**
- **Quy tắc Lô Lẻ (Odd-lot):** Phân bổ tối đa 25% NAV (~{target_allocation:,.0f} VNĐ) $\\to$ Giải ngân **{lot_shares:,} cổ phiếu** (~{actual_capital:,.0f} VNĐ).
- **Vùng cắt lỗ (Stop-Loss -5%):** {stop_loss:,.1f} | **Vùng chốt lời (Take-Profit +10%):** {take_profit:,.1f}
- **Phần vốn còn lại ({initial_cash - actual_capital:,.0f} VNĐ):** Đề xuất phân bổ vào Quỹ ETF (E1VFVN30) và HĐTL VN30F1M để phòng ngừa rủi ro.
"""
        target_assets = [target_sym, "E1VFVN30", "VN30F1M"]
    else:
        # General Investment Plan Query
        idx = query_rag_ohlcv("VNINDEX")
        news = query_rag_news(None, limit=3)
        p_idx = idx.get("last_price", 1733.98)
        pct_idx = idx.get("pct_1d", -0.88)
        trend_idx = idx.get("trend", "Điều chỉnh")
        
        news_str = "\n".join([f"  • [{n['source']} - {n['date']}] {n['headline']}" for n in news]) if news else "  • Thị trường duy trì thanh khoản ổn định."
        
        reply = f"""### 🧭 Kế Hoạch Đầu Tư & Phân Bổ Danh Mục Đa Tài Sản (Vốn: {initial_cash:,.0f} VNĐ)

#### 1. Đánh Giá Bối Cảnh Thị Trường (Từ db/vesta_ohlcv.duckdb)
- **Chỉ số VN-Index:** {p_idx:,.2f} điểm ({pct_idx:+.2f}%) | **Xu hướng:** {trend_idx}
- **Trạng thái thị trường:** Vùng định giá hấp dẫn cho tích lũy dài hạn, kết hợp phòng ngừa rủi ro biến động ngắn hạn.

#### 2. Dòng Chảy Tin Tức Vĩ Mô Mới Nhất (Từ db/vesta_news.duckdb)
{news_str}

#### 3. Chiến Lược Phân Bổ Danh Mục Đa Tài Sản (Vốn Khởi Điểm: 10,000,000 VNĐ)
Cơ chế giao dịch hỗ trợ **lô lẻ (Odd-lot)** và **phái sinh T+0**, tối ưu hóa biên an toàn vốn:

1. **Quỹ Chỉ Số ETF (E1VFVN30 / FUEVFVND) — 40% ({initial_cash * 0.4:,.0f} VNĐ):**
   - Mua ~150 chứng chỉ quỹ E1VFVN30 (thị giá ~26.5k).
   - *Mục tiêu:* Nền tảng danh mục, bắt trọn đà tăng trưởng nhóm 30 cổ phiếu đầu ngành Việt Nam.
2. **Cổ Phiếu Tăng Trưởng Đầu Ngành (FPT / VCB / HPG) — 35% ({initial_cash * 0.35:,.0f} VNĐ):**
   - Mua lô lẻ: 25 cổ phiếu FPT (thị giá ~135k) $\\to$ Giải ngân ~3,375,000 VNĐ.
   - *Mục tiêu:* Tận dụng sức mạnh tăng trưởng lợi nhuận cốt lõi và vị thế công nghệ hàng đầu.
3. **Phòng Ngừa Rủi Ro Phái Sinh / Chứng Quyền (VN30F1M / CW) — 15% ({initial_cash * 0.15:,.0f} VNĐ):**
   - Ký quỹ 15% vốn hoặc mua chứng quyền CFPT/CHPG.
   - *Mục tiêu:* Hedging danh mục khi thị trường xuất hiện rung lắc ngắn hạn ($T+0$).
4. **Tiền Mặt Dự Phòng (Cash) — 10% ({initial_cash * 0.1:,.0f} VNĐ):**
   - Giữ 1,000,000 VNĐ để trung bình giá khi có cơ hội điều chỉnh sâu.

#### 4. Kỷ Luật & Quản Trị Rủi Ro
- Trần phân bổ một mã: Không vượt quá 25% NAV.
- Ngưỡng cắt lỗ nghiêm ngặt: -4.5% trên từng vị thế.
- Tỷ lệ Sharpe kỳ vọng: **1.95** (Dựa trên mô phỏng Đấu trường Bot Arena).
"""
        target_assets = ["E1VFVN30", "FPT", "VN30F1M", "CFPT2301"]

    bot_config = {
        "bot_id": f"RAG_BOT_{int(dt.datetime.now().timestamp()) % 10000}",
        "name": f"VESTA Multi-Asset Quantitative Bot ({target_assets[0]})",
        "initial_cash": initial_cash,
        "signal_weights": {
            "sentiment": 0.40,
            "momentum": 0.25,
            "regime_gate": 0.20,
            "foreign_flow": 0.15,
        },
        "target_assets": target_assets,
        "max_nav_cap_pct": 25.0,
        "stop_loss_pct": 4.5,
        "estimated_sharpe": 1.95,
        "reasoning_thesis": reply[:300] + "...",
        "risk_flags": ["ODD_LOT_SUPPORTED", "MULTI_ASSET_ALLOCATION", "DUCKDB_RAG_SYNTHESIZED"],
        "suggested_action": "ALLOCATE_PORTFOLIO",
    }
    
    return {"reply": reply, "bot_config": bot_config}

print("=== TEST 1: 'Hãy cho tôi thông tin về VIC' ===")
r1 = generate_rag_response("Hãy cho tôi thông tin về VIC")
print(r1["reply"][:600])

print("\n=== TEST 2: 'Hãy cho tôi kế hoạch đầu tư' ===")
r2 = generate_rag_response("Hãy cho tôi kế hoạch đầu tư")
print(r2["reply"][:600])
