# Loop Verification: F401 & F402 — Inference Service & Feedback Log

## 1. Invariant & Hypothesis Contract
- **Features Included:**
  - `F401`: Local Inference Service (FastAPI/CLI, read-only, no trading logic).
  - `F402`: Feedback Log for scored predictions vs. realized returns ($t+5, t+30$).
- **Target State:** `not_started`
- **Architectural Invariant:**
  - Read-Only: Zero execution logic or broker credentials in `F401`.
  - Drift Monitoring: Every scored inference is logged with its inputs and back-filled with realized returns once future market bars become available.
  - Enables out-of-sample drift detection without capital risk.

## 2. Retrospective Progress Audit (2026-09-12 Consolidation)
- **Status:** **not_started** (Blocked by F302).
- **Service Scaffolding:** `src/service/` module structure ready.

## 3. 5-Gate Loop Verification Status
- [ ] **Gate 1 to Gate 5:** Pending completion of `F302`.

## 4. Verification Command & Evidence
```bash
pytest tests/test_inference_service.py tests/test_feedback_log.py -v
```
- **Exit Condition:** Remains `not_started` until `F302` completes.
