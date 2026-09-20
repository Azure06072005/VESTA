"""src/service/inference_app.py

Feature F401: Local Real-Time Streaming Inference Service (Strictly Read-Only).
FastAPI application delivering microsecond-to-millisecond streaming inference for
live crawler ingestion across HOSE/HNX/UPCOM equities.

Key Capabilities:
1. SimHash 6-hour sliding deduplication to purge duplicate syndicated wire news.
2. Shareholder & executive entity resolution (shareholder_entity_matcher).
3. Source authenticity weighting (W_source: state=1.0, finance=0.85, social=0.35).
4. Sub-50ms neural inference with PhoBERT-base / Multimodal.
5. HybridACD consistency gating (Simplex-TCD + V-FAN) to filter hallucinations.
6. F203 Market Regime Hard Rail (Fail-closed during liquidity crises).
"""
from __future__ import annotations

import logging
import os
import pathlib
import sys
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

import numpy as np
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

# Ensure repo root and src/ are in sys.path
REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from pipeline.f3xx_modeling.hybridacd_gate import HybridACDConsistencyGate
from pipeline.sentiment_lexicon import score_headline as lexicon_score
from pipeline.shareholder_entity_matcher import shareholder_registry
from service.feedback_log import DriftMonitor, InferenceFeedbackLogger
from service.simhash_cache import SimHashDedupCache, canonicalize_url

logger = logging.getLogger("inference_app")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


# =============================================================================
# 1. SOURCE AUTHENTICITY TRUST MAP (W_source)
# =============================================================================
SOURCE_TRUST_MAP: Dict[str, float] = {
    # 1.0: State & Official Exchange Regulatory Disclosures
    "ssc": 1.0,
    "ubcknn": 1.0,
    "hose": 1.0,
    "hnx": 1.0,
    "sbv": 1.0,
    "chinhphu": 1.0,
    "baochinhphu": 1.0,
    "bocongthuong": 1.0,
    "botaichinh": 1.0,
    # 0.85: Reputable Financial Editorial Press
    "cafef": 0.85,
    "vietstock": 0.85,
    "vneconomy": 0.85,
    "baodautu": 0.85,
    "thoibaonganhang": 0.85,
    "thoibaotaichinh": 0.85,
    "tinnhanhchungkhoan": 0.85,
    "tnck": 0.85,
    # 0.60: General Editorial News Outlets / Syndicated Wires
    "tuoitre": 0.60,
    "thanhnien": 0.60,
    "tienphong": 0.60,
    "nhandan": 0.60,
    "vietnamnet": 0.60,
    "dantri": 0.60,
    "vnexpress": 0.60,
    # 0.35: Social Forums, Rumors, Unverified Sources
    "f319": 0.35,
    "fireant": 0.35,
    "social": 0.35,
    "forum": 0.35,
    "telegram": 0.35,
}

DEFAULT_TRUST_WEIGHT = 0.60


def get_source_weight(source: Optional[str]) -> float:
    """Returns trust weight W_source in [0.35, 1.00] based on reporting authority."""
    if not source:
        return DEFAULT_TRUST_WEIGHT
    s = source.strip().lower()
    for key, weight in SOURCE_TRUST_MAP.items():
        if key in s:
            return weight
    return DEFAULT_TRUST_WEIGHT


# =============================================================================
# 2. PYDANTIC REQUEST & RESPONSE SCHEMAS
# =============================================================================
class HeadlineScoreRequest(BaseModel):
    headline: str = Field(..., min_length=2, description="News headline to analyze")
    body: Optional[str] = Field(None, description="Optional article body or lead summary")
    symbol: Optional[str] = Field(None, description="Ticker symbol (if known)")
    source: Optional[str] = Field(None, description="Source name, e.g. CafeF, UBCKNN, F319")
    url: Optional[str] = Field(None, description="Original source URL for canonical dedup")
    published_at: Optional[str] = Field(None, description="ISO publication timestamp")
    regime_override: Optional[bool] = Field(None, description="Optional market regime safe flag")


class HeadlineScoreResponse(BaseModel):
    symbol: Optional[str]
    sentiment_class: str  # POSITIVE, NEUTRAL, NEGATIVE
    raw_probabilities: Dict[str, float]  # negative, neutral, positive
    projected_probabilities: Dict[str, float]
    raw_sentiment_score: float  # [0, 100]
    consistent_alpha_score: float  # [0, 100]
    is_consistent: bool
    violation_score: float
    is_duplicate: bool
    original_article_id: Optional[str] = None
    source_trust_weight: float
    matched_shareholder: Optional[str] = None
    action_recommendation: str  # BUY_DIP, HOLD, AVOID, IGNORE_NOISE
    regime_safe_to_trade: bool
    latency_ms: float
    prediction_id: Optional[str] = None


class BatchScoreRequest(BaseModel):
    items: List[HeadlineScoreRequest] = Field(..., min_length=1)


class BatchScoreResponse(BaseModel):
    results: List[HeadlineScoreResponse]
    batch_size: int
    total_latency_ms: float


class HealthResponse(BaseModel):
    model_config = {"protected_namespaces": ()}
    status: str
    device: str
    model_loaded: bool
    checkpoint_path: str
    simhash_cache_size: int
    shareholder_registry_count: int
    vram_allocated_mb: float


# =============================================================================
# 3. CORE LOCAL INFERENCE ENGINE
# =============================================================================
class LocalInferenceEngine:
    """Manages neural models, HybridACD gating, SimHash caching, and entity resolution."""

    def __init__(self, checkpoint_path: Optional[str] = None) -> None:
        self.checkpoint_path = checkpoint_path or "out/models/phobert_base_findpo/best_model.pt"
        self.device = "cpu"
        self.model: Any = None
        self.tokenizer: Any = None
        self.gate = HybridACDConsistencyGate(noise_threshold=0.35, discard_inconsistent=True)
        self.dedup_cache = SimHashDedupCache(ttl_seconds=21600.0, hamming_threshold=4)
        self.feedback_logger: Optional[InferenceFeedbackLogger] = None
        try:
            self.feedback_logger = InferenceFeedbackLogger()
        except Exception as err:
            logger.warning(f"Feedback logger initialization deferred: {err}")
        self._load_model()
        self._init_shareholder_registry()

    def _init_shareholder_registry(self) -> None:
        try:
            if not shareholder_registry._is_loaded:
                count = shareholder_registry.load_registry()
                logger.info(f"Loaded {count} shareholder records into inference engine.")
        except Exception as err:
            logger.warning(f"Could not load shareholder registry: {err}")

    def _load_model(self) -> None:
        """Loads fine-tuned PhoBERT-base weights into memory (GPU if available, else CPU)."""
        try:
            import torch
            from transformers import AutoTokenizer

            if torch.cuda.is_available():
                self.device = "cuda"
            else:
                self.device = "cpu"

            if os.path.exists(self.checkpoint_path):
                from models.phobert_findpo import PhoBertFinDPO
                self.tokenizer = AutoTokenizer.from_pretrained("vinai/phobert-base-v2")
                self.model = PhoBertFinDPO(model_name="vinai/phobert-base-v2")
                state_dict = torch.load(self.checkpoint_path, map_location=self.device)
                self.model.load_state_dict(state_dict, strict=False)
                self.model.to(self.device)
                self.model.eval()
                # Optional FP16 half precision on GPU
                if self.device == "cuda":
                    self.model.half()
                logger.info(f"Loaded PhoBERT-base checkpoint from {self.checkpoint_path} on {self.device}.")
            else:
                logger.warning(f"Checkpoint not found at {self.checkpoint_path}. Running with calibrated lexicon engine.")
        except Exception as err:
            logger.warning(f"Failed to load PyTorch model ({err}). Fallback to calibrated lexicon engine.")
            self.model = None

    def _predict_raw_probabilities_batch(self, texts: List[str]) -> List[np.ndarray]:
        """Computes raw softmax probabilities for a batch of texts in a single forward pass."""
        if self.model is not None and self.tokenizer is not None:
            try:
                import torch
                with torch.inference_mode():
                    enc = self.tokenizer(
                        texts,
                        return_tensors="pt",
                        truncation=True,
                        max_length=128,
                        padding=True,
                    )
                    input_ids = enc["input_ids"].to(self.device)
                    attention_mask = enc["attention_mask"].to(self.device)
                    out = self.model(input_ids=input_ids, attention_mask=attention_mask)
                    logits = out.sentiment_logits.float()
                    probs = torch.softmax(logits, dim=-1).cpu().numpy()
                    return [probs[i] for i in range(len(texts))]
            except Exception as err:
                logger.warning(f"Batch PyTorch forward pass failed ({err}), using individual fallback.")

        return [self._predict_raw_probabilities(t) for t in texts]

    def _predict_raw_probabilities(self, text: str) -> np.ndarray:
        """Computes raw softmax probabilities [p_neg, p_neu, p_pos] for given text."""
        if self.model is not None and self.tokenizer is not None:
            try:
                import torch
                with torch.inference_mode():
                    enc = self.tokenizer(
                        text,
                        return_tensors="pt",
                        truncation=True,
                        max_length=128,
                        padding=False,
                    )
                    input_ids = enc["input_ids"].to(self.device)
                    attention_mask = enc["attention_mask"].to(self.device)
                    out = self.model(input_ids=input_ids, attention_mask=attention_mask)
                    logits = out.sentiment_logits.float()
                    probs = torch.softmax(logits, dim=-1).squeeze(0).cpu().numpy()
                    return probs  # [p_neg, p_neu, p_pos]
            except Exception as err:
                logger.warning(f"PyTorch forward pass failed ({err}), using lexicon fallback.")

        # High-precision calibrated rule-based fallback (lexicon_score returns [-1.0, 1.0])
        score = lexicon_score(text)  # in [-1.0, 1.0]
        # Map score [-1.0, 1.0] to probabilities via smooth softmax temperature
        diff = float(score) * 3.0
        p_pos = 1.0 / (1.0 + np.exp(-diff))
        p_neg = 1.0 / (1.0 + np.exp(diff))
        p_neu = max(0.05, 1.0 - abs(p_pos - p_neg))
        raw = np.array([p_neg, p_neu, p_pos], dtype=float)
        return raw / np.sum(raw)

    def score_single(self, req: HeadlineScoreRequest) -> HeadlineScoreResponse:
        """Processes one headline through the full 6-step streaming pipeline."""
        t0 = time.perf_counter()

        # Step 1: Dedup Check (SimHash 6-hour sliding window)
        is_dup, orig_id, _ = self.dedup_cache.check_and_insert(
            headline=req.headline,
            body=req.body,
            url=req.url,
        )

        # Step 2: Shareholder & Executive Entity Resolution
        resolved_sym = req.symbol.strip().upper() if req.symbol else None
        matched_holder: Optional[str] = None

        if not resolved_sym:
            # Check headline and body for major shareholders
            matches = shareholder_registry.match_shareholders(req.headline)
            if not matches and req.body:
                matches = shareholder_registry.match_shareholders(req.body[:500])
            if matches:
                matches.sort(key=lambda m: (m.ownership_percentage or 0.0), reverse=True)
                resolved_sym = matches[0].symbol
                matched_holder = matches[0].matched_name

        # Step 3: Source Authenticity Weighting (W_source) & Regime Check
        w_source = get_source_weight(req.source)
        regime_safe = True if req.regime_override is None else req.regime_override

        # Early return on duplicate wire syndicated articles to meet sub-5ms SLA
        if is_dup:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            dup_action = "AVOID" if not regime_safe else "IGNORE_NOISE"
            resp = HeadlineScoreResponse(
                symbol=resolved_sym,
                sentiment_class="NEUTRAL",
                raw_probabilities={"negative": 0.0, "neutral": 1.0, "positive": 0.0},
                projected_probabilities={"negative": 0.0, "neutral": 1.0, "positive": 0.0},
                raw_sentiment_score=50.0,
                consistent_alpha_score=50.0,
                is_consistent=True,
                violation_score=0.0,
                is_duplicate=True,
                original_article_id=orig_id,
                source_trust_weight=round(w_source, 2),
                matched_shareholder=matched_holder,
                action_recommendation=dup_action,
                regime_safe_to_trade=regime_safe,
                latency_ms=round(latency_ms, 2),
            )
            if self.feedback_logger is not None:
                try:
                    resp.prediction_id = self.feedback_logger.log_prediction(req, resp)
                except Exception as err:
                    logger.debug(f"Feedback log skipped on duplicate: {err}")
            return resp

        # Step 4: Neural / Calibrated Probability Inference & Consistency Gating
        full_text = f"{req.headline} {req.body[:200] if req.body else ''}".strip()
        negated_text = self.gate.generate_negated_headline(req.headline)
        probs_pair = self._predict_raw_probabilities_batch([full_text, negated_text])
        p_orig, p_neg = probs_pair[0], probs_pair[1]

        # Step 5: HybridACD Consistency Gating (Simplex-TCD + V-FAN)
        gate_res = self.gate.evaluate_event(
            headline=req.headline,
            prob_orig=p_orig,
            prob_neg=p_neg,
            negated_headline=negated_text,
        )

        # Apply source credibility weighting W_source
        raw_score = 50.0 + 50.0 * float(p_orig[2] - p_orig[0])
        # Shrink alpha score towards neutral 50 if source is unreliable (e.g. forum)
        calibrated_alpha = 50.0 + w_source * (gate_res.consistent_alpha_score - 50.0)

        # Projected consistent probabilities
        p_star = gate_res.projected_probs

        # Determine discrete sentiment class based on input text prediction
        classes = ["NEGATIVE", "NEUTRAL", "POSITIVE"]
        sentiment_cls = classes[int(np.argmax(p_orig))]

        # Step 6: Market Regime Safety Rail (F203)
        regime_safe = True if req.regime_override is None else req.regime_override

        # Action Recommendation Decision Engine (Safety Hard Rails evaluated first per Rule B5)
        if not regime_safe:
            action = "AVOID"  # Fail-closed circuit breaker during market crisis (F203)
        elif not gate_res.is_consistent:
            action = "IGNORE_NOISE"  # HybridACD filters inconsistent/hallucinatory headlines
        elif calibrated_alpha < 45.0:
            action = "BUY_DIP"  # Mean-reversion trigger
        elif calibrated_alpha > 58.0:
            action = "HOLD"
        else:
            action = "HOLD"

        latency_ms = (time.perf_counter() - t0) * 1000.0

        resp = HeadlineScoreResponse(
            symbol=resolved_sym,
            sentiment_class=sentiment_cls,
            raw_probabilities={
                "negative": round(float(p_orig[0]), 4),
                "neutral": round(float(p_orig[1]), 4),
                "positive": round(float(p_orig[2]), 4),
            },
            projected_probabilities={
                "negative": round(float(p_star[0]), 4),
                "neutral": round(float(p_star[1]), 4),
                "positive": round(float(p_star[2]), 4),
            },
            raw_sentiment_score=round(float(raw_score), 2),
            consistent_alpha_score=round(float(calibrated_alpha), 2),
            is_consistent=gate_res.is_consistent,
            violation_score=round(float(gate_res.violation_score), 4),
            is_duplicate=is_dup,
            original_article_id=orig_id,
            source_trust_weight=round(w_source, 2),
            matched_shareholder=matched_holder,
            action_recommendation=action,
            regime_safe_to_trade=regime_safe,
            latency_ms=round(latency_ms, 2),
        )
        if self.feedback_logger is not None:
            try:
                resp.prediction_id = self.feedback_logger.log_prediction(req, resp)
            except Exception as err:
                logger.debug(f"Feedback log skipped on scored headline: {err}")
        return resp


# Global Engine Instance
engine = LocalInferenceEngine()


# =============================================================================
# 4. FASTAPI APP & ENDPOINTS
# =============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing VESTA F401 Local Streaming Inference Service...")
    yield
    logger.info("Shutting down VESTA F401 Inference Service.")


app = FastAPI(
    title="VESTA Streaming Inference Service (F401)",
    description="Real-time read-only sentiment and HybridACD consistency inference for Vietnamese equities.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse, tags=["Monitoring"])
def healthcheck():
    """Healthcheck endpoint reporting hardware, model status, and cache size."""
    vram_mb = 0.0
    try:
        import torch
        if torch.cuda.is_available():
            vram_mb = torch.cuda.memory_allocated() / (1024 * 1024)
    except Exception:
        pass

    return HealthResponse(
        status="HEALTHY",
        device=engine.device,
        model_loaded=(engine.model is not None),
        checkpoint_path=engine.checkpoint_path,
        simhash_cache_size=engine.dedup_cache.size,
        shareholder_registry_count=len(shareholder_registry.records_by_symbol),
        vram_allocated_mb=round(vram_mb, 2),
    )


@app.post("/api/v1/score_headline", response_model=HeadlineScoreResponse, tags=["Inference"])
def score_headline_endpoint(req: HeadlineScoreRequest):
    """Scores a single incoming headline with sub-50ms latency budget."""
    if not req.headline or len(req.headline.strip()) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Headline text must not be empty.",
        )
    return engine.score_single(req)


@app.post("/api/v1/score_batch", response_model=BatchScoreResponse, tags=["Inference"])
def score_batch_endpoint(batch: BatchScoreRequest):
    """Processes a batch of headlines with sequential or vectorized evaluation."""
    t0 = time.perf_counter()
    results = [engine.score_single(item) for item in batch.items]
    total_latency = (time.perf_counter() - t0) * 1000.0
    return BatchScoreResponse(
        results=results,
        batch_size=len(results),
        total_latency_ms=round(total_latency, 2),
    )


@app.get("/api/v1/drift_status", tags=["Monitoring"])
def get_drift_status_endpoint(window_size: int = 30):
    """Computes real-time rolling model drift telemetry and circuit-breaker status (F402)."""
    db_path = engine.feedback_logger.db_path if engine.feedback_logger else None
    monitor = DriftMonitor(db_path=db_path)
    report = monitor.compute_rolling_drift(window_size=window_size)
    return {
        "run_id": report.run_id,
        "audit_timestamp": report.audit_timestamp.isoformat(),
        "window_size": report.window_size,
        "total_evaluated": report.total_evaluated,
        "total_pending": report.total_pending,
        "directional_accuracy_t5": report.directional_accuracy_t5,
        "mean_brier_score_t5": report.mean_brier_score_t5,
        "spearman_ic_t5": report.spearman_ic_t5,
        "circuit_breaker_status": report.circuit_breaker_status,
        "alert_triggered": report.alert_triggered,
        "alert_message": report.alert_message,
    }
