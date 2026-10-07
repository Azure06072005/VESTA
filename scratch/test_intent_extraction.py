import duckdb
import json
import re

def extract_symbols_and_intent(msg: str):
    msg_upper = msg.upper()
    
    # 1. Known special assets
    special_known = ["VN30F1M", "VN30F2M", "GB05F", "E1VFVN30", "FUEVFVND", "FUESSVFL", "VNINDEX", "VN30", "HNX", "UPCOM"]
    found_symbols = []
    for sa in special_known:
        if sa in msg_upper:
            found_symbols.append(sa)
            
    # 2. Regex for 3-letter stock tickers
    candidates = re.findall(r'\b[A-Z]{3}\b', msg_upper)
    for c in candidates:
        if c not in found_symbols and c not in ["BOT", "VND", "VND", "ALL", "THE", "AND", "FOR"]:
            found_symbols.append(c)
            
    # 3. Check lowercase mentions like 'cổ phiếu vic', 'mã fpt'
    m = re.search(r'(?:cổ phiếu|mã|cp)\s+([a-zA-Z0-9]{3,8})', msg, re.IGNORECASE)
    if m:
        sym = m.group(1).upper()
        if sym not in found_symbols:
            found_symbols.insert(0, sym)
            
    # Intent detection
    is_info_query = any(k in msg.lower() for k in ["cho tôi thông tin", "thông tin về", "tình hình", "báo cáo tài chính", "giá cổ phiếu", "doanh nghiệp", "phân tích mã"])
    is_defense = any(k in msg.lower() for k in ["phòng thủ", "hạ rủi ro", "biến động mạnh", "hedging", "bảo toàn", "phòng vệ", "an toàn"])
    is_aggressive = any(k in msg.lower() for k in ["tấn công", "đột phá", "breakout", "siêu lợi nhuận", "lãi cao", "đòn bẩy"])
    
    return {
        "symbols": found_symbols,
        "is_info_query": is_info_query,
        "is_defense": is_defense,
        "is_aggressive": is_aggressive,
    }

print("Test 1 (VN30 defensive):", extract_symbols_and_intent("Tôi muốn thiết kế một bot phòng thủ cho rổ VN30 và phái sinh VN30F1M khi thị trường biến động mạnh, vốn 10 triệu VNĐ."))
print("Test 2 (Info VIC):", extract_symbols_and_intent("cho tôi thông tin về cổ phiếu VIC"))
print("Test 3 (FPT analysis):", extract_symbols_and_intent("Phân tích tình hình cổ phiếu FPT"))
