"""test_pipeline/f1xx_enrichment/test_text_preprocessing_suite.py

Pytest suite validating Step 5: Text Preprocessing, Deduplication & Entity Disambiguation.
Invariants:
1. SBV Disambiguation: Pure SBV policy maker mentions do NOT map to Sector 11 (Banking).
2. Administrative Boilerplate: Official headers/footers/stamps are strictly stripped.
3. Exact Duplicate Identification: Identical texts achieve MinHash Jaccard == 1.0000.
4. Near-Duplicate Syndication: Syndicated press releases achieve MinHash Jaccard >= 0.80.
5. Corporate Misrouted Filter: Dividend/corporate filings inside macro_policy are identified.
"""
from __future__ import annotations

import pytest

from test_pipeline.f1xx_enrichment.test_text_preprocessing_and_disambiguation import (
    normalize_text,
    disambiguate_banking_entities,
    MinHashLSH,
    POLICY_PILLARS,
)


def test_sbv_vs_commercial_bank_disambiguation():
    """Invariant 1: Pure SBV administrative news must NOT trigger Sector 11 (Commercial Banking)."""
    # Case A: Pure SBV administrative news (e.g. appointment or delegation)
    t_pure = "Ngân hàng Nhà nước bổ nhiệm Phó Vụ trưởng Vụ Hợp tác Quốc tế"
    has_sbv, is_sector_11 = disambiguate_banking_entities(t_pure, "")
    assert has_sbv is True
    assert is_sector_11 is False, "Pure SBV administrative news should NOT be assigned to Sector 11!"

    # Case B: SBV policy with direct commercial banking operational impact
    t_comm = "Ngân hàng Nhà nước nới room tín dụng cho các ngân hàng thương mại để hạ lãi suất cho vay"
    has_sbv, is_sector_11 = disambiguate_banking_entities(t_comm, "")
    assert has_sbv is True
    assert is_sector_11 is True, "SBV policy with commercial banking context MUST trigger Sector 11!"


def test_administrative_boilerplate_stripping():
    """Invariant 2: Administrative and media boilerplate are cleanly stripped from text."""
    raw = (
        "(Chinhphu.vn) - Cộng hòa xã hội chủ nghĩa Việt Nam Độc lập - Tự do - Hạnh phúc. "
        "Thủ tướng Chính phủ ban hành Chỉ thị về đẩy mạnh giải ngân vốn đầu tư công. "
        "Nơi nhận: các Bộ, ban ngành. Ký thay Thủ tướng: Phó Thủ tướng Lê Minh Khái."
    )
    clean = normalize_text(raw, is_policy=True)
    
    assert "(chinhphu.vn)" not in clean.lower()
    assert "độc lập - tự do - hạnh phúc" not in clean.lower()
    assert "nơi nhận:" not in clean.lower()
    assert "ký thay thủ tướng" not in clean.lower()
    assert "chỉ thị về đẩy mạnh giải ngân vốn đầu tư công" in clean.lower()


def test_exact_duplicate_minhash_jaccard_one():
    """Invariant 3: Identical texts achieve MinHash Jaccard similarity of 1.0000."""
    t1 = "Chính phủ vừa ban hành Nghị định 08 tháo gỡ khó khăn cho thị trường trái phiếu doanh nghiệp"
    t2 = "Chính phủ vừa ban hành Nghị định 08 tháo gỡ khó khăn cho thị trường trái phiếu doanh nghiệp"
    
    lsh = MinHashLSH(num_perm=64)
    sig1 = lsh.compute_signature(t1)
    sig2 = lsh.compute_signature(t2)
    
    jaccard = (sig1 == sig2).mean()
    assert jaccard == 1.0, f"Expected exact duplicate Jaccard = 1.0, got {jaccard}"


def test_near_duplicate_syndication_detection():
    """Invariant 4: Syndicated news with minor editorial changes achieve MinHash Jaccard >= 0.80."""
    # Source A (Báo Chính phủ)
    t_gov = "Ngân hàng Nhà nước quyết định giảm lãi suất điều hành lần thứ tư trong năm nhằm hỗ trợ tăng trưởng kinh tế"
    # Source B (Tin Nhanh Chứng Khoán copy with minor header/footer)
    t_tnck = "Nóng: Ngân hàng Nhà nước quyết định giảm lãi suất điều hành lần thứ tư trong năm nhằm hỗ trợ tăng trưởng kinh tế. Theo TNCK."
    
    clean_gov = normalize_text(t_gov, is_policy=True)
    clean_tnck = normalize_text(t_tnck, is_policy=False)
    
    lsh = MinHashLSH(num_perm=64)
    sig1 = lsh.compute_signature(clean_gov)
    sig2 = lsh.compute_signature(clean_tnck)
    
    jaccard = (sig1 == sig2).mean()
    assert jaccard >= 0.80, f"Expected near-duplicate Jaccard >= 0.80, got {jaccard:.4f}"


def test_misrouted_corporate_filings_detection():
    """Invariant 5: Single-stock dividend announcements in macro_policy are identified for rerouting."""
    t_div = "BLN: Ngày GDKHQ trả cổ tức năm 2025 bằng tiền (10%)"
    clean = normalize_text(t_div, is_policy=True)
    
    is_misrouted = bool(POLICY_PILLARS["MISROUTED_CORPORATE"]["pattern"].search(clean))
    assert is_misrouted is True, "Dividend headline inside macro_policy MUST be flagged as MISROUTED_CORPORATE!"
