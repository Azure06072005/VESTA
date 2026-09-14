"""Unit Test Suite for Module 1: Gray Code Encoding (Enhanced Scope & Canonical Boundaries).

Locks mathematical invariants:
1. Invariant 1: Hamming distance is strictly 1 for all adjacent transitions G(n) -> G(n+1).
2. Invariant 2: Scope Gray Code preserves topological distance H(VN_DOMESTIC, BOTH) = 1, H(BOTH, GLOBAL) = 1.
3. Invariant 3: Bijective mapping is lossless and reversible (gray_to_int(int_to_gray(n)) == n).
4. Invariant 4: Canonical REGIME_BOUNDARIES mapping correctly classifies dates across all 16 historical epochs.
5. Invariant 5: Neural activation jumps have significantly lower peak shock than standard binary.
"""
from __future__ import annotations

import pytest
from test_pipeline.f1xx_enrichment.test_gray_code_encoding import (
    HISTORICAL_SUB_EVENTS,
    REGIME_BOUNDARIES,
    SCOPE_TO_GRAY,
    encode_macro_state_gray,
    gray_bits_to_int,
    gray_to_int,
    hamming_distance,
    int_to_binary_bits,
    int_to_gray,
    int_to_gray_bits,
    map_date_to_regime_info,
    simulate_neural_activation_jump,
)


def test_hamming_distance_is_strictly_one_for_all_transitions():
    """Validates that EVERY adjacent transition in canonical REGIME_BOUNDARIES has Hamming distance exactly 1."""
    n_states = len(REGIME_BOUNDARIES)
    for i in range(n_states - 1):
        g1 = int_to_gray_bits(i, 4)
        g2 = int_to_gray_bits(i + 1, 4)
        dist = hamming_distance(g1, g2)
        assert dist == 1, f"Transition {i} -> {i+1} ({REGIME_BOUNDARIES[i][0]} -> {REGIME_BOUNDARIES[i+1][0]}) has Hamming distance {dist} != 1!"


def test_scope_gray_code_topological_distance():
    """Validates that Scope Gray Code has Hamming distance 1 between adjacent scopes."""
    assert hamming_distance(SCOPE_TO_GRAY["VN_DOMESTIC"], SCOPE_TO_GRAY["BOTH"]) == 1
    assert hamming_distance(SCOPE_TO_GRAY["BOTH"], SCOPE_TO_GRAY["GLOBAL"]) == 1
    assert hamming_distance(SCOPE_TO_GRAY["VN_DOMESTIC"], SCOPE_TO_GRAY["GLOBAL"]) == 2


def test_bijective_encoding_decoding_invertibility():
    """Validates that encoding and decoding are perfectly bijective across 0..63."""
    for n in range(64):
        g = int_to_gray(n)
        recovered = gray_to_int(g)
        assert recovered == n, f"Failed integer roundtrip for {n}: got {recovered}"

        bits = int_to_gray_bits(n, 6)
        recovered_bits = gray_bits_to_int(bits)
        assert recovered_bits == n, f"Failed bit roundtrip for {n}: got {recovered_bits}"


def test_canonical_regime_and_scope_mapping_exhaustiveness():
    """Validates that key historical dates in Vietnam stock history correctly map to their canonical regime & scope."""
    test_cases = [
        ("2001-05-15", 0, "dotcom_bubble_crash_vn", "BOTH"),
        ("2004-06-10", 1, "post_bubble_consolidation", "VN_DOMESTIC"),
        ("2006-12-20", 2, "pre_gfc_bull_run", "VN_DOMESTIC"),
        ("2008-10-15", 3, "gfc_crash", "BOTH"),
        ("2010-04-20", 4, "post_gfc_recovery", "BOTH"),
        ("2012-05-10", 5, "euro_debt_crisis_overlay", "GLOBAL"),
        ("2014-08-15", 6, "steady_growth", "BOTH"),
        ("2017-06-01", 7, "bull_run_2016_2018", "VN_DOMESTIC"),
        ("2018-10-10", 8, "bear_market_2018_2019", "BOTH"),
        ("2020-03-20", 9, "covid_crash", "BOTH"),
        ("2021-06-01", 10, "covid_recovery_rally", "BOTH"),
        ("2022-10-15", 11, "real_estate_bond_crisis_2022", "BOTH"),
        ("2024-05-20", 12, "recovery_2023_2024", "VN_DOMESTIC"),
        ("2025-06-01", 13, "tariff_shock_ftse_rally_2025", "BOTH"),
        ("2025-11-15", 14, "ftse_upgrade_correction", "VN_DOMESTIC"),
        ("2026-05-20", 15, "pre_upgrade_run_2026", "BOTH"),
    ]
    for date_str, expected_idx, expected_id, expected_scope in test_cases:
        idx, r_id, scope, _ = map_date_to_regime_info(date_str)
        assert idx == expected_idx, f"Date {date_str} mapped to idx {idx} != {expected_idx}"
        assert r_id == expected_id, f"Date {date_str} mapped to {r_id} != {expected_id}"
        assert scope == expected_scope, f"Date {date_str} scope {scope} != {expected_scope}"


def test_combined_macro_gray_code_vector():
    """Validates 6-bit combined vector generation and historical sub-event detection."""
    # Test during FLC / bond crisis sub-event (concurrent with Russia-Ukraine shock)
    res = encode_macro_state_gray("2022-04-10")
    assert len(res["macro_gray_6b"]) == 6
    assert res["regime_id"] == "real_estate_bond_crisis_2022"
    assert res["scope"] == "BOTH"
    assert "flc_thm_vtp_crackdown" in res["active_sub_events"]
    assert "russia_ukraine_commodity_spike" in res["active_sub_events"]

    # Test during Bau Kien arrest
    res_kien = encode_macro_state_gray("2012-08-25")
    assert "bau_kien_acb_arrest" in res_kien["active_sub_events"]


def test_neural_activation_gradient_smoothness_advantage():
    """Validates that Gray code has lower maximum transition shock than standard binary."""
    jumps_gray, mean_g, max_g = simulate_neural_activation_jump("gray", weight_seed=42)
    jumps_bin, mean_b, max_b = simulate_neural_activation_jump("binary", weight_seed=42)

    assert max_b > max_g, f"Expected standard binary max jump ({max_b:.4f}) > Gray code max jump ({max_g:.4f})"
    ratio_g = max_g / mean_g
    assert ratio_g < 2.0, f"Gray code shock ratio {ratio_g:.2f} is too erratic!"
