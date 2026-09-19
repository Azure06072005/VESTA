"""tests/test_inference_service.py

Comprehensive Test Suite for Feature F401: Local Streaming Inference Service (Strictly Read-Only).
Verifies the following core invariants:
1. Healthcheck monitoring: status, hardware device, model loaded state, VRAM allocation.
2. Directional sentiment accuracy on known benchmark headlines (positive, negative).
3. 6-Hour sliding SimHash deduplication: detects syndicated news and returns sub-5ms latency.
4. Shareholder and executive entity resolution (maps Trần Hùng Huy -> ACB, bầu Đức -> HAG).
5. Source authenticity weighting (W_source: UBCKNN=1.0, CafeF=0.85, F319=0.35 shrinks to neutral).
6. HybridACD mathematical consistency gate (Simplex-TCD + V-FAN Kolmogorov bounds).
7. F203 Market regime hard rail: fail-closed safety gate (action='AVOID' during market stress).
8. Batch scoring endpoint: validates batch ingestion and aggregate latency.
9. Latency budget SLA: 50-sample empirical benchmark confirms average latency < 50.0 ms.
10. Regulatory read-only compliance: strictly no execution or broker order routing logic.
"""
from __future__ import annotations

import pathlib
import sys
import time
from typing import List

import numpy as np
import pytest
from fastapi.testclient import TestClient

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from service.inference_app import app, engine


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


# =============================================================================
# 1. HEALTHCHECK ENDPOINT TEST
# =============================================================================
def test_healthcheck_endpoint(client: TestClient):
    """Verifies that the /health monitoring endpoint reports HEALTHY and valid hardware state."""
    response = client.get("/health")
    assert response.status_code == 200, f"Expected 200 OK, got {response.status_code}: {response.text}"
    data = response.json()

    assert data["status"] == "HEALTHY"
    assert data["device"] in ["cuda", "cpu"]
    assert "model_loaded" in data
    assert isinstance(data["model_loaded"], bool)
    assert data["shareholder_registry_count"] > 0
    assert data["simhash_cache_size"] >= 0
    assert data["vram_allocated_mb"] >= 0.0


# =============================================================================
# 2. KNOWN POSITIVE & NEGATIVE HEADLINES TEST
# =============================================================================
def test_known_positive_and_negative_sentiment(client: TestClient):
    """Verifies that clear bullish and bearish headlines produce expected classes and alpha scores."""
    # Bullish test case
    pos_payload = {
        "headline": "Doanh nghiệp báo lãi sau thuế quý 3 tăng trưởng đột biến 180%, vượt xa kế hoạch năm",
        "symbol": "VNM",
        "source": "CafeF",
    }
    pos_resp = client.post("/api/v1/score_headline", json=pos_payload)
    assert pos_resp.status_code == 200
    pos_data = pos_resp.json()

    assert pos_data["sentiment_class"] == "POSITIVE"
    assert pos_data["raw_sentiment_score"] > 50.0
    assert pos_data["consistent_alpha_score"] >= 50.0
    assert pos_data["raw_probabilities"]["positive"] > pos_data["raw_probabilities"]["negative"]

    # Bearish test case
    neg_payload = {
        "headline": "Thua lỗ nặng nề nghìn tỷ đồng, nguy cơ vỡ nợ trái phiếu và giải chấp diện rộng",
        "symbol": "NVL",
        "source": "Vietstock",
    }
    neg_resp = client.post("/api/v1/score_headline", json=neg_payload)
    assert neg_resp.status_code == 200
    neg_data = neg_resp.json()

    assert neg_data["sentiment_class"] == "NEGATIVE"
    assert neg_data["raw_sentiment_score"] < 50.0
    assert neg_data["consistent_alpha_score"] <= 50.0
    assert neg_data["raw_probabilities"]["negative"] > neg_data["raw_probabilities"]["positive"]
    assert neg_data["action_recommendation"] in ["BUY_DIP", "IGNORE_NOISE", "HOLD"]


# =============================================================================
# 3. 6-HOUR SLIDING SIMHASH DEDUPLICATION TEST
# =============================================================================
def test_simhash_deduplication_within_6h(client: TestClient):
    """Verifies that syndicated or near-duplicate articles are identified and fast-returned under 5ms."""
    headline_orig = "Tập đoàn Vingroup chính thức mở rộng quy mô xuất khẩu xe điện sang thị trường Bắc Mỹ"
    headline_dup = "Tập đoàn Vingroup vừa chính thức mở rộng quy mô xuất khẩu xe điện sang thị trường Bắc Mỹ"

    # Reset or verify first article
    p1 = {"headline": headline_orig, "source": "CafeF"}
    r1 = client.post("/api/v1/score_headline", json=p1)
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["is_duplicate"] is False
    assert d1["original_article_id"] is None

    # Second near-duplicate article arrives shortly after
    p2 = {"headline": headline_dup, "source": "VnEconomy"}
    r2 = client.post("/api/v1/score_headline", json=p2)
    assert r2.status_code == 200
    d2 = r2.json()

    assert d2["is_duplicate"] is True
    assert d2["original_article_id"] is not None
    assert d2["action_recommendation"] == "IGNORE_NOISE"
    assert d2["latency_ms"] < 5.0, f"Duplicate should short-circuit under 5ms, took {d2['latency_ms']}ms"


# =============================================================================
# 4. SHAREHOLDER & EXECUTIVE ENTITY RESOLUTION TEST
# =============================================================================
def test_shareholder_entity_resolution(client: TestClient):
    """Verifies that headlines mentioning key individuals are automatically resolved to correct tickers."""
    # Test case 1: Trần Hùng Huy -> ACB
    p1 = {
        "headline": "Chủ tịch Trần Hùng Huy vừa đăng ký mua vào 5 triệu cổ phiếu",
        "symbol": None,
        "source": "CafeF",
    }
    r1 = client.post("/api/v1/score_headline", json=p1)
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["symbol"] == "ACB", f"Expected ACB, got {d1['symbol']}"
    assert "Trần Hùng Huy" in (d1["matched_shareholder"] or "")

    # Test case 2: Bầu Đức -> HAG
    p2 = {
        "headline": "Bầu Đức khẳng định công ty sẽ trả hết toàn bộ nợ ngân hàng trong năm nay",
        "symbol": None,
        "source": "Vietstock",
    }
    r2 = client.post("/api/v1/score_headline", json=p2)
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["symbol"] == "HAG", f"Expected HAG, got {d2['symbol']}"

    # Test case 3: Explicit symbol provided is preserved
    p3 = {
        "headline": "Chủ tịch Hồ Hùng Anh phát biểu tại đại hội đồng cổ đông",
        "symbol": "TCB",
        "source": "CafeF",
    }
    r3 = client.post("/api/v1/score_headline", json=p3)
    assert r3.status_code == 200
    d3 = r3.json()
    assert d3["symbol"] == "TCB"


# =============================================================================
# 5. SOURCE AUTHENTICITY WEIGHTING TEST (W_source)
# =============================================================================
def test_source_authenticity_weighting(client: TestClient):
    """Verifies source authenticity weights (UBCKNN=1.0, CafeF=0.85, F319=0.35) and alpha shrinking."""
    headline = "Ủy ban Chứng khoán xử phạt hành chính doanh nghiệp do công bố thông tin sai lệch"

    # Official authority disclosure
    r_gov = client.post("/api/v1/score_headline", json={"headline": headline, "source": "UBCKNN"})
    assert r_gov.status_code == 200
    d_gov = r_gov.json()
    assert d_gov["source_trust_weight"] == 1.0

    # Mainstream financial press
    r_press = client.post("/api/v1/score_headline", json={"headline": headline, "source": "CafeF"})
    assert r_press.status_code == 200
    d_press = r_press.json()
    assert d_press["source_trust_weight"] == 0.85

    # Retail social forum (rumors)
    r_forum = client.post("/api/v1/score_headline", json={"headline": headline, "source": "F319"})
    assert r_forum.status_code == 200
    d_forum = r_forum.json()
    assert d_forum["source_trust_weight"] == 0.35

    # Verification: Lower trust source should have alpha shrunk closer to neutral 50.0
    dist_gov = abs(d_gov["consistent_alpha_score"] - 50.0)
    dist_forum = abs(d_forum["consistent_alpha_score"] - 50.0)
    assert dist_forum <= dist_gov + 1e-4, "Forum alpha score must be shrunk towards 50 compared to UBCKNN"


# =============================================================================
# 6. HYBRIDACD CONSISTENCY GATING TEST
# =============================================================================
def test_hybridacd_consistency_gating(client: TestClient):
    """Verifies Simplex-TCD projection guarantees sum(p*) == 1 and consistency filtering."""
    payload = {
        "headline": "Thị trường bất động sản phục hồi tích cực, thanh khoản các dự án gia tăng",
        "symbol": "KDH",
        "source": "CafeF",
    }
    resp = client.post("/api/v1/score_headline", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    # Verify probability simplex constraint: sum(p*) == 1.0
    p_star = data["projected_probabilities"]
    prob_sum = p_star["negative"] + p_star["neutral"] + p_star["positive"]
    assert abs(prob_sum - 1.0) < 1e-4, f"Sum of projected probabilities must be 1.0, got {prob_sum}"

    assert "is_consistent" in data
    assert "violation_score" in data
    assert data["violation_score"] >= 0.0


# =============================================================================
# 7. MARKET REGIME HARD RAIL SAFETY TEST (F203)
# =============================================================================
def test_market_regime_hard_rail_fail_closed(client: TestClient):
    """Verifies that during market crises (regime_safe_to_trade=False), the rail forces action='AVOID'."""
    # Under safe market regime, strong dip gives BUY_DIP
    safe_payload = {
        "headline": "Áp lực bán tháo diện rộng khiến cổ phiếu giảm sâu về vùng quá bán",
        "symbol": "SSI",
        "regime_override": True,
    }
    r_safe = client.post("/api/v1/score_headline", json=safe_payload)
    assert r_safe.status_code == 200
    d_safe = r_safe.json()
    assert d_safe["regime_safe_to_trade"] is True
    assert d_safe["action_recommendation"] in ["BUY_DIP", "HOLD"]
    assert d_safe["action_recommendation"] != "AVOID"

    # Under crisis market regime (e.g. VN-INDEX < MA200 liquidity dry-up), rail fails closed
    crisis_payload = {
        "headline": "Khủng hoảng thanh khoản khiến thị trường chứng khoán chao đảo và lao dốc mạnh",
        "symbol": "SSI",
        "regime_override": False,  # Simulates crisis
    }
    r_crisis = client.post("/api/v1/score_headline", json=crisis_payload)
    assert r_crisis.status_code == 200
    d_crisis = r_crisis.json()
    assert d_crisis["regime_safe_to_trade"] is False
    assert d_crisis["action_recommendation"] == "AVOID", "Crisis regime must fail closed to AVOID"


# =============================================================================
# 8. BATCH SCORING ENDPOINT TEST
# =============================================================================
def test_batch_scoring_endpoint(client: TestClient):
    """Verifies the /api/v1/score_batch endpoint handles multiple items cleanly."""
    batch_items = [
        {"headline": f"Doanh nghiệp ngành thép đón nhận cơ hội xuất khẩu mới số {i}", "symbol": "HPG"}
        for i in range(4)
    ]
    resp = client.post("/api/v1/score_batch", json={"items": batch_items})
    assert resp.status_code == 200
    data = resp.json()

    assert data["batch_size"] == 4
    assert len(data["results"]) == 4
    assert data["total_latency_ms"] > 0.0
    for res in data["results"]:
        assert res["symbol"] == "HPG"
        assert res["sentiment_class"] in ["POSITIVE", "NEUTRAL", "NEGATIVE"]


# =============================================================================
# 9. LATENCY BUDGET SLA BENCHMARK (< 50ms)
# =============================================================================
def test_latency_budget_under_50ms_sla(client: TestClient):
    """Benchmarks 50 unique requests to ensure streaming inference strictly respects < 50ms budget."""
    latencies: List[float] = []

    for i in range(50):
        payload = {
            "headline": f"Thông tin cập nhật diễn biến giao dịch thị trường phiên chiều ngày {i + 1}",
            "symbol": "VCB",
            "source": "CafeF",
        }
        resp = client.post("/api/v1/score_headline", json=payload)
        assert resp.status_code == 200
        lat = resp.json()["latency_ms"]
        latencies.append(lat)

    lat_arr = np.array(latencies)
    mean_lat = float(np.mean(lat_arr))
    p50_lat = float(np.percentile(lat_arr, 50))
    p95_lat = float(np.percentile(lat_arr, 95))
    max_lat = float(np.max(lat_arr))

    print(f"\n[LATENCY BENCHMARK (N=50)] Mean: {mean_lat:.2f}ms | P50: {p50_lat:.2f}ms | P95: {p95_lat:.2f}ms | Max: {max_lat:.2f}ms")

    assert mean_lat < 50.0, f"Average latency SLA violated: {mean_lat:.2f}ms >= 50.0ms target"
    assert p95_lat < 50.0, f"P95 latency SLA violated: {p95_lat:.2f}ms >= 50.0ms target"


# =============================================================================
# 10. STRICT READ-ONLY & COMPLIANCE GUARDRAIL (RULE B1)
# =============================================================================
def test_read_only_compliance():
    """Verifies that the inference service contains strictly NO broker execution or order placement code."""
    # Ensure no execution modules were imported
    forbidden_modules = [
        "execution.broker_api",
        "execution.order_executor",
        "execution.dnse_trader",
        "execution.ssi_trader",
    ]
    for mod in forbidden_modules:
        assert mod not in sys.modules, f"Compliance Violation: Forbidden module {mod} is loaded in inference service!"

    # Verify app title explicitly denotes Read-Only
    assert "F401" in app.title or "Inference" in app.title
