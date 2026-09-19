"""src/pipeline/macro_context_detector.py

Advanced Macroeconomic Policy Lexicon & Context Detection Framework for Vietnamese Financial Markets.

Analyzes raw text from core.macro_policy (Government decrees, SBV directives, Prime Minister circulars)
and detects multi-tier sentiment, contrastive clause shifts, and policy-to-market latent inversions.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


def strip_accents(s: str) -> str:
    """Normalize and strip diacritics for deterministic matching, handling Vietnamese đ/Đ."""
    s = s.replace("đ", "d").replace("Đ", "d")
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return s.lower()


# =============================================================================
# 1. MACROECONOMIC POLICY TAXONOMY (Hệ Từ Vựng Chính Sách Vĩ Mô Đa Tầng)
# =============================================================================

# 1.1. Chính sách tiền tệ & Lãi suất điều hành
MONETARY_EASING_TERMS: tuple[str, ...] = (
    "ha lai suat",                 # Hạ lãi suất
    "giam lai suat",               # Giảm lãi suất
    "lai suat giam",               # Lãi suất giảm
    "mat bang lai suat giam",      # Mặt bằng lãi suất giảm
    "ha lai suat dieu hanh",       # Hạ lãi suất điều hành
    "giam lai suat tai cap von",   # Giảm lãi suất tái cấp vốn
    "giam lai suat tai chiet khau",# Giảm lãi suất tái chiết khấu
    "ha tran lai suat huy dong",   # Hạ trần lãi suất huy động
    "noi long tien te",            # Nới lỏng tiền tệ
    "bom thanh khoan",             # Bơm thanh khoản
    "bom rong qua omo",            # Bơm ròng qua kênh OMO
    "ho tro thanh khoan",          # Hỗ trợ thanh khoản hệ thống
    "giam chi phi von",            # Giảm chi phí vốn cho doanh nghiệp
)

MONETARY_TIGHTENING_TERMS: tuple[str, ...] = (
    "tang lai suat",               # Tăng lãi suất
    "lai suat tang",               # Lãi suất tăng
    "tang lai suat dieu hanh",     # Tăng lãi suất điều hành
    "tang lai suat tai cap von",   # Tăng lãi suất tái cấp vốn
    "that chat tien te",           # Thắt chặt tiền tệ
    "siet thanh khoan",            # Siết thanh khoản
    "hut rong",                    # Hút ròng
    "hut rong qua tin phieu",      # Hút ròng qua tín phiếu SBV
    "phat hanh tin phieu",         # Phát hành tín phiếu
    "tin phieu sbv",               # Tín phiếu SBV
    "hut tien ve",                 # Hút tiền về
    "kiem soat lam phat",          # Kiểm soát lạm phát
)

# 1.2. Tỷ giá & Can thiệp ngoại hối (FX & Reserves)
FX_PRESSURE_TERMS: tuple[str, ...] = (
    "ap luc ty gia",               # Áp lực tỷ giá
    "ty gia trung tam tang",       # Tỷ giá trung tâm tăng
    "ty gia tang manh",            # Tỷ giá tăng mạnh
    "mat gia dong viet",           # Mất giá tiền đồng VND
    "dong viet mat gia",           # Đồng Việt mất giá
    "can thiep ty gia",            # Can thiệp tỷ giá
    "ban usd can thiep",           # Bán USD can thiệp
    "ban ngoai te",                # Bán ngoại tệ
    "can kiet du tru ngoai hoi",   # Cạn kiệt dự trữ ngoại hối
    "khoi ngoai rut von",          # Khối ngoại rút vốn ròng
    "chenh lech lai suat am",      # Chênh lệch lãi suất USD-VND âm
    "dxy vuot dinh",               # Chỉ số DXY vượt đỉnh
    "dxy tang cao",                # DXY tăng cao
)

FX_STABILIZATION_TERMS: tuple[str, ...] = (
    "on dinh ty gia",              # Ổn định tỷ giá
    "ty gia ha nhiet",             # Tỷ giá hạ nhiệt
    "ty gia di ngang",             # Tỷ giá đi ngang
    "ty gia trung tam di ngang",   # Tỷ giá trung tâm đi ngang
    "ty gia trung tam giam",       # Tỷ giá trung tâm giảm
    "du tru ngoai hoi doi dao",    # Dự trữ ngoại hối dồi dào
    "kieu hoi tang truong",        # Kiều hối tăng trưởng mạnh
    "thang du thuong mai",         # Thặng dư thương mại
    "dong fdi giai ngan manh",     # Dòng vốn FDI giải ngân mạnh
)

# 1.3. Tín dụng & Thị trường Bất động sản (Credit & Real Estate)
CREDIT_EXPANSION_TERMS: tuple[str, ...] = (
    "noi room tin dung",           # Nới room tín dụng
    "giao het chi tieu tin dung",  # Giao toàn bộ chỉ tiêu tín dụng
    "tang truong tin dung",        # Tăng trưởng tín dụng
    "giai ngan goi 120000 ty",     # Giải ngân gói 120.000 tỷ nhà ở xã hội
    "thao go phap ly du an",       # Tháo gỡ pháp lý dự án bất động sản
    "go kho bat dong san",         # Gỡ khó bất động sản
    "ha chuan tin dung",           # Hạ chuẩn cho vay
)

DEBT_DISTRESS_TERMS: tuple[str, ...] = (
    "ap luc dao han trai phieu",   # Áp lực đáo hạn trái phiếu doanh nghiệp
    "no cham tra",                 # Nợ chậm trả gốc lãi
    "mat kha nang tra no",         # Mất khả năng trả nợ
    "kho khan dong tien",          # Khó khăn dòng tiền
    "no xau tang",                 # Nợ xấu tăng
    "no nhom 2 tang",              # Nợ nhóm 2 (cần chú ý) tăng
    "dong bang bat dong san",      # Đóng băng bất động sản
)

# 1.4. Chính sách tài khóa & Đầu tư công (Fiscal Policy & Capex)
FISCAL_STIMULUS_TERMS: tuple[str, ...] = (
    "dau tu cong",                 # Đầu tư công
    "day manh dau tu cong",        # Đẩy mạnh đầu tư công
    "giai ngan dau tu cong",       # Giải ngân đầu tư công bứt phá
    "cao toc bac nam",             # Cao tốc Bắc Nam
    "san bay long thanh",          # Sân bay Long Thành
    "giam thue vat",               # Giảm 2% thuế VAT
    "chinh sach tai khoa mo rong", # Chính sách tài khóa mở rộng
    "goi kich thich kinh te",      # Gói kích thích kinh tế
    "von moi",                     # Vốn mồi dẫn dắt đầu tư tư nhân
)

# 1.5. Cơ chế giãn hoãn nợ & Khung pháp lý tái cấu trúc (Evergreening Regulatory Shields)
REGULATORY_SHIELD_TERMS: tuple[str, ...] = (
    "thong tu 02",                 # Thông tư 02/2023/TT-NHNN
    "gian no",                     # Giãn nợ
    "hoan no",                     # Hoãn nợ
    "giu nguyen nhom no",          # Giữ nguyên nhóm nợ
    "gia han thong tu 02",         # Gia hạn Thông tư 02
    "nghi dinh 08",                # Nghị định 08/2023/NĐ-CP về trái phiếu
    "nghi dinh 65",                # Nghị định 65 sửa đổi
    "nghi dinh 200",               # Nghị định mới về trái phiếu
    "thao go the kho",             # Tháo gỡ thế khó
)

# =============================================================================
# 1.6. FLEXIBLE CLAUSE PATTERNS (Cụm từ linh hoạt xử lý đảo ngữ và xen kẽ phó từ)
# =============================================================================
FLEXIBLE_CATEGORY_REGEX = {
    "MONETARY_EASING": re.compile(r"\b(ha|giam)\b.{0,18}\blai suat\b|\blai suat\b.{0,18}\b(ha|giam)\b", re.IGNORECASE),
    "MONETARY_TIGHTENING": re.compile(r"\btang\b.{0,18}\blai suat\b|\blai suat\b.{0,18}\btang\b", re.IGNORECASE),
    "FX_PRESSURE": re.compile(r"\b(ap luc|cang thang|mat gia)\b.{0,18}\bty gia\b|\bty gia\b.{0,18}\b(tang manh|cang thang|ap luc)\b", re.IGNORECASE),
    "FX_STABILIZATION": re.compile(r"\b(on dinh|ha nhiet)\b.{0,18}\bty gia\b|\bty gia\b.{0,18}\b(on dinh|ha nhiet|di ngang)\b", re.IGNORECASE),
}


# =============================================================================
# 2. CONTRASTIVE CONJUNCTIONS (Liên Từ Đối Lập Tiếng Việt)
# Note: "song" must exclude "lan song" (wave), "song nganh", "dong song"
# =============================================================================
CONTRASTIVE_PATTERNS = re.compile(
    r"\b(nhung|tuy nhien|the nhung|mac du|dang chu y la|trai lai|nguoc lai|"
    r"(?<!lan\s)(?<!dong\s)(?<!con\s)song(?!\sgio)(?!\sthan)(?!\snganh))\b",
    re.IGNORECASE,
)


@dataclass
class MacroContextResult:
    headline: str
    cleaned_text: str
    dominant_category: str
    surface_sentiment: str          # "positive", "negative", "neutral"
    latent_sentiment: str           # "positive", "negative", "neutral"
    has_contrastive_shift: bool
    contrastive_shift_detail: Optional[str]
    inversion_risk_flag: Optional[str]
    confidence_score: float         # [0.0, 1.0]
    macro_alpha_impact: float       # [-1.0, +1.0]


def analyze_macro_policy_headline(headline: str, body: Optional[str] = None) -> MacroContextResult:
    """Analyze a single macroeconomic policy headline and detect multi-tier latent market impact.

    Identifies:
    1. Surface Sentiment vs Latent Market Sentiment.
    2. Contrastive shifts across clauses (e.g. 'Lãi suất giảm nhưng tỷ giá căng thẳng').
    3. Structural policy inversions (e.g. Rate cuts causing capital flight).
    """
    raw_text = headline + (" " + body[:300] if body else "")
    norm_text = strip_accents(raw_text)

    # 1. Check Category Matches (Exact terms + Flexible regex matching)
    scores: Dict[str, int] = {
        "MONETARY_EASING": sum(1 for term in MONETARY_EASING_TERMS if term in norm_text) + (2 if FLEXIBLE_CATEGORY_REGEX["MONETARY_EASING"].search(norm_text) else 0),
        "MONETARY_TIGHTENING": sum(1 for term in MONETARY_TIGHTENING_TERMS if term in norm_text) + (2 if FLEXIBLE_CATEGORY_REGEX["MONETARY_TIGHTENING"].search(norm_text) else 0),
        "FX_PRESSURE": sum(1 for term in FX_PRESSURE_TERMS if term in norm_text) + (2 if FLEXIBLE_CATEGORY_REGEX["FX_PRESSURE"].search(norm_text) else 0),
        "FX_STABILIZATION": sum(1 for term in FX_STABILIZATION_TERMS if term in norm_text) + (2 if FLEXIBLE_CATEGORY_REGEX["FX_STABILIZATION"].search(norm_text) else 0),
        "CREDIT_EXPANSION": sum(1 for term in CREDIT_EXPANSION_TERMS if term in norm_text),
        "DEBT_DISTRESS": sum(1 for term in DEBT_DISTRESS_TERMS if term in norm_text),
        "FISCAL_STIMULUS": sum(1 for term in FISCAL_STIMULUS_TERMS if term in norm_text),
        "REGULATORY_SHIELD": sum(1 for term in REGULATORY_SHIELD_TERMS if term in norm_text),
    }

    dominant_cat = max(scores, key=scores.get)
    max_score = scores[dominant_cat]
    if max_score == 0:
        dominant_cat = "GENERAL_MACRO"

    # 2. Check Contrastive Conjunctions
    has_contrastive = bool(CONTRASTIVE_PATTERNS.search(norm_text))
    shift_detail = None

    if has_contrastive:
        parts = CONTRASTIVE_PATTERNS.split(norm_text, maxsplit=1)
        if len(parts) >= 3:
            pre_clause, conj, post_clause = parts[0], parts[1], parts[2]
            shift_detail = f"Pre: [{pre_clause.strip()[:40]}] -> {conj} -> Post: [{post_clause.strip()[:40]}]"

    # 3. Determine Surface vs Latent Sentiment & Inversion Risk Flags
    inversion_flag = None
    surface_sentiment = "neutral"
    latent_sentiment = "neutral"
    macro_alpha = 0.0

    # CASE A: Monetary Easing with FX Pressure (Capital flight trap)
    if scores["MONETARY_EASING"] > 0 and scores["FX_PRESSURE"] > 0:
        surface_sentiment = "positive"  # Surface: Rate cut sounds bullish
        latent_sentiment = "negative"   # Latent: SBV cutting rates under DXY pressure -> foreign sell-off
        inversion_flag = "RATE_CUT_CAPITAL_FLIGHT_RISK"
        macro_alpha = -0.45

    # CASE B: SBV Bill Issuance / Excess Liquidity Mop-up (Panic dip but medium-term stabilization)
    elif "hut rong qua tin phieu" in norm_text or "phat hanh tin phieu" in norm_text:
        surface_sentiment = "negative"  # Surface: Retail panics thinking SBV is draining credit
        latent_sentiment = "positive"   # Latent: Only mopping excess interbank cash to defend FX without selling reserves -> buying opportunity
        inversion_flag = "SBV_BILL_MOP_UP_DIP_REVERSAL"
        macro_alpha = +0.50

    # CASE C: Regulatory Shield (Circular 02 / Decree 08 debt restructuring)
    elif scores["REGULATORY_SHIELD"] > 0:
        surface_sentiment = "positive"  # Surface: Relief for property developers
        latent_sentiment = "neutral"    # Latent: Simply delaying non-performing loans (Evergreening), property market remains frozen
        inversion_flag = "DEBT_EVERGREENING_SHIELD"
        macro_alpha = +0.10

    # CASE D: Pure Fiscal Stimulus (Infrastructure capex, long-term positive spillover)
    elif scores["FISCAL_STIMULUS"] > 0:
        surface_sentiment = "positive"
        latent_sentiment = "positive"
        macro_alpha = +0.65

    # CASE E: Pure Debt Distress
    elif scores["DEBT_DISTRESS"] > 0:
        surface_sentiment = "negative"
        latent_sentiment = "negative"
        macro_alpha = -0.60

    # CASE F: Pure FX Pressure
    elif scores["FX_PRESSURE"] > 0:
        surface_sentiment = "negative"
        latent_sentiment = "negative"
        macro_alpha = -0.55

    # CASE G: Pure Monetary Easing
    elif scores["MONETARY_EASING"] > 0:
        surface_sentiment = "positive"
        latent_sentiment = "positive"
        macro_alpha = +0.60

    # CASE H: Pure Monetary Tightening
    elif scores["MONETARY_TIGHTENING"] > 0:
        surface_sentiment = "negative"
        latent_sentiment = "negative"
        macro_alpha = -0.50

    # CASE I: Pure FX Stabilization
    elif scores["FX_STABILIZATION"] > 0:
        surface_sentiment = "positive"
        latent_sentiment = "positive"
        macro_alpha = +0.45

    # CASE J: Pure Credit Expansion
    elif scores["CREDIT_EXPANSION"] > 0:
        surface_sentiment = "positive"
        latent_sentiment = "positive"
        macro_alpha = +0.50

    # Default
    else:
        surface_sentiment = "neutral"
        latent_sentiment = "neutral"
        macro_alpha = 0.0

    # Adjust confidence
    confidence = min(0.5 + 0.15 * max_score + (0.2 if inversion_flag else 0.0), 0.98)

    return MacroContextResult(
        headline=headline,
        cleaned_text=norm_text[:120],
        dominant_category=dominant_cat,
        surface_sentiment=surface_sentiment,
        latent_sentiment=latent_sentiment,
        has_contrastive_shift=has_contrastive,
        contrastive_shift_detail=shift_detail,
        inversion_risk_flag=inversion_flag,
        confidence_score=round(confidence, 3),
        macro_alpha_impact=round(macro_alpha, 3),
    )
