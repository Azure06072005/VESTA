"""tests/test_macro_context_detector.py

Unit tests for the Advanced Macroeconomic Policy Lexicon & Context Detector.
Validates multi-tier sentiment, contrastive clause shifts, and policy-to-market latent inversions.
"""
import pytest
from src.pipeline.macro_context_detector import (
    analyze_macro_policy_headline,
    strip_accents,
    MacroContextResult,
)


def test_strip_accents_vietnamese_d():
    """Verify that Vietnamese 'đ' and 'Đ' are normalized properly to 'd'."""
    assert strip_accents("Ổn định") == "on dinh"
    assert strip_accents("Điều hành chính sách") == "dieu hanh chinh sach"
    assert strip_accents("Đầu tư công") == "dau tu cong"


def test_pure_monetary_easing():
    """Verify monetary easing policy yields positive latent alpha."""
    res = analyze_macro_policy_headline("Hạ lãi suất điều hành để hỗ trợ phục hồi sản xuất kinh doanh")
    assert res.dominant_category == "MONETARY_EASING"
    assert res.surface_sentiment == "positive"
    assert res.latent_sentiment == "positive"
    assert res.macro_alpha_impact > 0.0
    assert res.inversion_risk_flag is None


def test_monetary_easing_flexible_word_order():
    """Verify flexible word order with adverbs (sẽ giảm dần) matches MONETARY_EASING."""
    res = analyze_macro_policy_headline("Maybank: Mặt bằng lãi suất sẽ giảm dần vào nửa cuối năm")
    assert res.dominant_category == "MONETARY_EASING"
    assert res.latent_sentiment == "positive"
    assert res.macro_alpha_impact > 0.0


def test_capital_flight_inversion_trap():
    """Verify rate cut under FX pressure triggers RATE_CUT_CAPITAL_FLIGHT_RISK."""
    res = analyze_macro_policy_headline("Hạ lãi suất nhưng áp lực tỷ giá gia tăng mạnh khi DXY vượt đỉnh")
    assert res.surface_sentiment == "positive"
    assert res.latent_sentiment == "negative"
    assert res.inversion_risk_flag == "RATE_CUT_CAPITAL_FLIGHT_RISK"
    assert res.macro_alpha_impact < 0.0
    assert res.has_contrastive_shift is True
    assert "nhung" in (res.contrastive_shift_detail or "")


def test_sbv_bill_mop_up_inversion():
    """Verify SBV bill issuance (panic dip reversal) triggers positive latent alpha."""
    res = analyze_macro_policy_headline("NHNN tiếp tục hút ròng qua tín phiếu nhằm ổn định thị trường tiền tệ")
    assert res.surface_sentiment == "negative"
    assert res.latent_sentiment == "positive"
    assert res.inversion_risk_flag == "SBV_BILL_MOP_UP_DIP_REVERSAL"
    assert res.macro_alpha_impact > 0.0


def test_regulatory_shield_evergreening():
    """Verify Circular 02 / Decree 08 debt restructuring triggers DEBT_EVERGREENING_SHIELD."""
    res = analyze_macro_policy_headline("Gia hạn Thông tư 02 về cơ cấu nợ và giữ nguyên nhóm nợ cho doanh nghiệp")
    assert res.dominant_category == "REGULATORY_SHIELD"
    assert res.surface_sentiment == "positive"
    assert res.latent_sentiment == "neutral"
    assert res.inversion_risk_flag == "DEBT_EVERGREENING_SHIELD"


def test_disambiguation_lan_song_vs_conjunction():
    """Verify 'làn sóng' (wave) is NOT mistaken for the conjunction 'song' (however)."""
    # 1. 'Làn sóng' should not trigger contrastive shift
    res1 = analyze_macro_policy_headline("Làn sóng giảm giá nhà ở lan rộng do áp lực thanh khoản")
    assert res1.has_contrastive_shift is False

    # 2. 'song' as a conjunction SHOULD trigger contrastive shift
    res2 = analyze_macro_policy_headline("Thanh khoản dồi dào song dòng tiền ngoại vẫn e dè")
    assert res2.has_contrastive_shift is True
    assert "song" in (res2.contrastive_shift_detail or "")
