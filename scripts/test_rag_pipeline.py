import duckdb
import re
import datetime as dt
from typing import Dict, Any, List, Optional

SNAPSHOT_DB = "db/vesta_snapshot.duckdb"
NEWS_DB = "db/vesta_news.duckdb"
OHLCV_DB = "db/vesta_ohlcv.duckdb"

def extract_symbols_from_query(query: str) -> List[str]:
    """Trích xuất mã chứng khoán hoặc phái sinh từ câu hỏi."""
    tokens = re.findall(r'\b[A-Z0-9]{3,8}\b', query.upper())
    common_stops = {'HAY', 'CHO', 'TOI', 'BAN', 'THE', 'NAO', 'MUA', 'BAN', 'GIA', 'CO', 'DUNG', 'TIEN', 'VND', 'BOT', 'SLM', 'COT'}
    symbols = [t for t in tokens if t not in common_stops and not t.isdigit()]
    return symbols

def query_rag_ohlcv(symbol: str) -> Dict[str, Any]:
    with duckdb.connect(OHLCV_DB, read_only=True) as con:
        # Check if index
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
        
        # Simple RSI(14)
        if len(closes) >= 15:
            diffs = [closes[i] - closes[i+1] for i in range(14)]
            gains = [d for d in diffs if d > 0]
            losses = [-d for d in diffs if d < 0]
            avg_gain = sum(gains) / 14 if gains else 0.001
            avg_loss = sum(losses) / 14 if losses else 0.001
            rs = avg_gain / avg_loss
            rsi14 = round(100 - (100 / (1 + rs)), 1)
        else:
            rsi14 = 50.0
            
        trend = "Tăng (Bullish)" if p_last > sma20 >= sma50 else ("Giảm (Bearish)" if p_last < sma20 else "Đi ngang (Neutral)")
        
        return {
            "symbol": symbol,
            "found": True,
            "last_date": str(latest[0]),
            "last_price": p_last,
            "pct_1d": pct_1d,
            "sma20": sma20,
            "sma50": sma50,
            "rsi14": rsi14,
            "high_52w": high_52w,
            "low_52w": low_52w,
            "avg_vol_20": round(sum(float(r[5]) for r in rows[:20]) / min(len(rows), 20)),
            "trend": trend,
        }

def query_rag_news(symbol: Optional[str] = None, limit: int = 4) -> List[Dict[str, Any]]:
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

def query_rag_snapshot(symbol: Optional[str] = None) -> Dict[str, Any]:
    with duckdb.connect(SNAPSHOT_DB, read_only=True) as con:
        res = {"company_name": "", "exchange": "", "industry": "", "events": [], "shareholders": []}
        if not symbol:
            return res
            
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

print("Testing RAG for VIC:")
ohlcv_vic = query_rag_ohlcv("VIC")
news_vic = query_rag_news("VIC")
snap_vic = query_rag_snapshot("VIC")
print("OHLCV:", ohlcv_vic)
print("News count:", len(news_vic), "First headline:", news_vic[0]['headline'] if news_vic else None)
print("Snapshot:", snap_vic)

print("\nTesting RAG for general investment plan:")
ohlcv_vnindex = query_rag_ohlcv("VNINDEX")
news_macro = query_rag_news(None)
print("VNINDEX:", ohlcv_vnindex)
print("Macro News count:", len(news_macro), "First headline:", news_macro[0]['headline'] if news_macro else None)
