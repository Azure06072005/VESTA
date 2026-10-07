import duckdb
import json
import re

def handle_chat_test(msg: str):
    msg_upper = msg.upper()
    special_known = ["VN30F1M", "VN30F2M", "GB05F", "E1VFVN30", "FUEVFVND", "FUESSVFL", "VNINDEX", "VN30"]
    found_symbols = []
    for sa in special_known:
        if sa in msg_upper:
            found_symbols.append(sa)

    m = re.search(r'(?:cổ phiếu|mã|cp)\s+([a-zA-Z0-9]{3,8})', msg, re.IGNORECASE)
    if m:
        sym = m.group(1).upper()
        if sym not in found_symbols:
            found_symbols.insert(0, sym)

    stop_words = {"CHO", "TIN", "MOT", "KHI", "GIA", "BAN", "MUA", "VND", "RO", "BOT", "ALL", "THE", "AND", "NAY"}
    candidates = re.findall(r'\b[A-Z]{3}\b', msg_upper)
    for c in candidates:
        if c not in found_symbols and c not in stop_words:
            found_symbols.append(c)

    is_info_query = any(k in msg.lower() for k in [
        "cho tôi thông tin", "thông tin về", "tình hình", "báo cáo tài chính", 
        "giá cổ phiếu", "doanh nghiệp", "phân tích mã", "xem cổ phiếu", "thông tin mã"
    ])
    is_defense = any(k in msg.lower() for k in [
        "phòng thủ", "hạ rủi ro", "biến động mạnh", "hedging", "bảo toàn", "phòng vệ", "an toàn", "rủi ro"
    ])

    primary_sym = found_symbols[0] if found_symbols else ("VN30F1M" if is_defense else "FPT")
    print(f"Query: '{msg}'")
    print(f"  -> Extracted: primary={primary_sym}, is_info={is_info_query}, is_defense={is_defense}")

handle_chat_test("Tôi muốn thiết kế một bot phòng thủ cho rổ VN30 và phái sinh VN30F1M khi thị trường biến động mạnh, vốn 10 triệu VNĐ.")
handle_chat_test("cho tôi thông tin về cổ phiếu VIC")
handle_chat_test("phân tích mã FPT cho tôi")
