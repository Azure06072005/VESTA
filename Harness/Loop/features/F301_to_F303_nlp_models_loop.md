# Loop Verification: F301 to F303 — NLP Sentiment Modeling & Consistency Gate

## 1. Invariant & Hypothesis Contract
- **Features Included:**
  - `F301`: PhoBERT-base fine-tuning on Vietnamese financial news (VRAM budget: RTX 3060 6GB, fp16, gradient accumulation).
  - `F302`: Re-running `F201` backtest using fine-tuned SLM sentiment scores.
  - `F303`: HybridACD Token-Constrained Decoding consistency gate ($P(\text{pos}) + P(\text{neg\_negation}) = 1$).
- **Target State:** `not_started` (Strictly Blocked by `F203`)
- **Architectural Invariant:**
  - Rule B2 (Signal Before Infrastructure): Deep neural network fine-tuning cannot begin until `F203` resolves regime stability.
  - Memory Invariant: Peak VRAM allocation $\le 5.5\text{ GB}$ on RTX 3060 (enforced via `--dry-run-memory`).
  - Empirical Justification: `F302` must beat starter lexicon effect size / significance within noise tolerance to justify `F301`'s operational complexity.

## 2. Retrospective Progress Audit (2026-09-12 Consolidation)
- **Status:** **BLOCKED by F203**.
- **Model Scaffolding:** `src/models/train_sentiment.py` and `configs/phobert_base.yaml` scaffolded.
- **Dataset Source:** Prepared to ingest `core.pit_events` filtered according to the `F203` architectural decision.

## 3. 5-Gate Loop Verification Status
- [ ] **Gate 1 to Gate 5:** Pending completion of `F203`.

## 4. Verification Command & Evidence
```bash
python -m models.train_sentiment --config configs/phobert_base.yaml --dry-run-memory && pytest tests/test_sentiment_eval.py -x
```
- **Exit Condition:** Remains `not_started` until `F203` transitions to `passing`.
