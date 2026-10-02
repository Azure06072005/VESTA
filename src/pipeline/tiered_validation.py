"""
Khung Thẩm Định Chất Lượng Đa Tầng (Tiered Validation Penalty Framework - TVPF)
Hiện thực hóa recommendation F101: Chuyển đổi từ cơ chế loại bỏ nhị phân (Fail-Loudly)
sang chấm điểm chất lượng dữ liệu liên tục (Data Quality Scoring - DQS in [0.0, 1.0]).
Tuân thủ nghiêm ngặt Quy tắc B4 (Point-in-Time, zero look-ahead bias).
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Tuple
import duckdb
import pandas as pd


# Các cấp độ chất lượng dữ liệu
TIER_A_PRISTINE = "TIER_A_PRISTINE"       # DQS >= 0.90: Hoàn hảo, đầy đủ mọi trường
TIER_B_USABLE = "TIER_B_USABLE"           # 0.70 <= DQS < 0.90: Đủ chuẩn huấn luyện ML/Backtest
TIER_C_DEGRADED = "TIER_C_DEGRADED"       # 0.40 <= DQS < 0.70: Khiếm khuyết nhẹ, cần lag/weight thấp
TIER_D_UNRELIABLE = "TIER_D_UNRELIABLE"   # 0.00 < DQS < 0.40: Độ tin cậy rất thấp
TIER_1_REJECT = "TIER_1_REJECT"           # DQS = 0.00: Loại bỏ hoàn toàn (Fatal error)


def evaluate_event_dqs(row: Dict[str, Any] | pd.Series) -> Tuple[float, str, str]:
    """
    Tính điểm Data Quality Score (DQS) và gắn nhãn phân hạng chất lượng cho 1 sự kiện PIT.
    Returns:
        (dqs_score: float, flags: str, quality_tier: str)
    """
    penalties = 0.0
    flags: List[str] = []

    # 1. Tier 1: Fatal Errors (Penalty: 1.0 -> Exclude completely)
    price_pub = row.get("price_at_publish")
    if price_pub is None or (isinstance(price_pub, (int, float)) and price_pub <= 0):
        penalties += 1.0
        flags.append("TIER1_ZERO_PRICE")

    pub_at = row.get("published_at")
    fetch_at = row.get("fetched_at")
    if pub_at is not None and fetch_at is not None:
        if isinstance(pub_at, str):
            pub_at = pd.to_datetime(pub_at)
        if isinstance(fetch_at, str):
            fetch_at = pd.to_datetime(fetch_at)
        if pub_at > fetch_at + dt.timedelta(minutes=5):
            penalties += 1.0
            flags.append("TIER1_LOOKAHEAD_TIMING")

    # Nếu dính lỗi Tier 1: Loại bỏ ngay lập tức với điểm 0.0
    if penalties >= 1.0:
        return 0.0, " | ".join(flags), TIER_1_REJECT

    # 2. Tier 2: Structural Flaws (Penalty: 0.40)
    price_t1 = row.get("price_t1")
    if price_t1 is None or pd.isna(price_t1):
        penalties += 0.40
        flags.append("TIER2_MISSING_T1_RETURN")

    # 3. Tier 3: Metadata / Incompleteness Flaws (Penalty: 0.15 - 0.20)
    pub_time = row.get("pub_time")
    if pub_time is None and pub_at is not None:
        pub_time = pub_at.strftime("%H:%M:%S") if hasattr(pub_at, "strftime") else str(pub_at)[11:19]
    if pub_time == "00:00:00":
        penalties += 0.20
        flags.append("TIER3_MIDNIGHT_TIMESTAMP")

    body = row.get("body")
    if body is None or pd.isna(body) or len(str(body).strip()) < 50:
        penalties += 0.15
        flags.append("TIER3_HEADLINE_ONLY")

    bctc = row.get("fundamentals_json")
    if bctc is None or pd.isna(bctc) or str(bctc).strip() in ("", "{}", "None"):
        penalties += 0.15
        flags.append("TIER3_MISSING_BCTC")

    # 4. Tier 4: Minor Information Friction (Penalty: 0.05)
    price_t30 = row.get("price_t30")
    price_t5 = row.get("price_t5")
    if (price_t30 is None or pd.isna(price_t30)) and (price_t5 is not None and not pd.isna(price_t5)):
        penalties += 0.05
        flags.append("TIER4_INSUFFICIENT_T30_HORIZON")

    dqs = max(0.0, round(1.0 - penalties, 2))

    if dqs >= 0.90:
        tier_cat = TIER_A_PRISTINE
    elif dqs >= 0.70:
        tier_cat = TIER_B_USABLE
    elif dqs >= 0.40:
        tier_cat = TIER_C_DEGRADED
    elif dqs > 0.0:
        tier_cat = TIER_D_UNRELIABLE
    else:
        tier_cat = TIER_1_REJECT

    flag_str = " | ".join(flags) if flags else "CLEAN"
    return dqs, flag_str, tier_cat


def audit_tiered_quality(con: duckdb.DuckDBPyConnection, sample_size: int = 10000) -> Dict[str, Any]:
    """
    Thực hiện kiểm toán chất lượng đa tầng trên hồ dữ liệu và trả về báo cáo tóm tắt.
    """
    query = f"""
        SELECT 
            e.symbol,
            e.source_url,
            e.price_at_publish,
            e.price_t1,
            e.price_t5,
            e.price_t30,
            e.fundamentals_json,
            n.published_at,
            n.fetched_at,
            n.body,
            strftime(n.published_at, '%H:%M:%S') as pub_time
        FROM core.pit_events e
        JOIN news_db.core.news n ON e.source_url = n.source_url
        LIMIT {sample_size}
    """
    df = con.execute(query).df()
    if df.empty:
        return {"error": "No records found in core.pit_events"}

    scores, flags_list, tiers = [], [], []
    for _, r in df.iterrows():
        s, f, t = evaluate_event_dqs(r)
        scores.append(s)
        flags_list.append(f)
        tiers.append(t)

    df["dqs"] = scores
    df["quality_tier"] = tiers
    df["flags"] = flags_list

    tier_counts = df["quality_tier"].value_counts().to_dict()
    usable_rate = float((df["dqs"] >= 0.70).mean())
    reject_rate = float((df["quality_tier"] == TIER_1_REJECT).mean())

    return {
        "sample_size": len(df),
        "mean_dqs": float(df["dqs"].mean()),
        "median_dqs": float(df["dqs"].median()),
        "usable_rate": usable_rate,
        "reject_rate": reject_rate,
        "tier_distribution": tier_counts,
    }
