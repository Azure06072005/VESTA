# Verification Commands — VESTA

Only full-pipeline verification counts (Principle 10). Every line below
should be copy-pasteable and give a clean pass/fail signal.

| Check       | Command                                                         |
|-------------|------------------------------------------------------------------|
| Install     | `pip install -r requirements.txt --break-system-packages`        |
| Tests       | `pytest -x`                                                       |
| Lint        | `ruff check src tests`                                            |
| Type-check  | `mypy src tests --ignore-missing-imports`                         |
| Build       | `python -m build --wheel` *(only if packaging is needed; else N/A — a pure pipeline repo may skip this row, note why in DECISIONS.md if so)* |
| Smoke run   | `python -m pipeline.validate_crossref --all && python -m pipeline.backtest_meanreversion --report out/smoke_report.json --dry-run` |

## Per-feature verification (in addition to the table above)

Each feature in `feature_list.json` also has its own scoped command — the
table above is the repo-wide gate; the feature's own `verification` field is
the feature-specific gate. **Both must pass** before a feature moves to
`passing`.

Example:
```
F001 verification: pytest tests/test_dim_symbol.py -x
Repo-wide gate:     pytest -x && ruff check src tests && mypy src tests --ignore-missing-imports
```

## GPU/hardware-specific checks

- `models/train_sentiment.py` runs must be confirmed to fit VRAM budget:
  add `--dry-run-memory` flag that reports peak allocated VRAM before a full
  training run; fail the smoke run if peak > 5.5 GB (leaves headroom on the
  6GB RTX 3060 card).
- Any run touching `data/` should confirm available disk on the NVMe target
  drive before large fetches (`df -h` check in crawler startup, not a manual
  step).

## Notes

- `TODO` rows above must be replaced with real commands before any feature
  is allowed to move to `passing` — an agent hitting a literal `TODO` in
  this table should treat it as a blocker and stop, not guess a command.
- If `ruff`/`mypy`/`pytest` aren't yet installed in the environment, that's
  part of `init.sh`'s job (Install row) — verification should never require
  ad-hoc setup beyond what `init.sh` establishes.