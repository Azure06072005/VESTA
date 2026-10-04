# F501 deep instruction: Multi-Bot Strategy Arena (Monte Carlo)

## 0. Decisions
| # | Decision | Reason |
|---|---|---|
| D1 | Bots are **composites of strategy components**, with the registry as the source of truth. The 5 original personas become named composites in that registry. | Maximum coverage and combined multi-strategy support. |
| D2 | **N for DSR = effective number of independent trials**, estimated by clustering bot return correlations, with raw N=308 as the conservative bound. Never N=5. | Avoid overstated DSR in large multi-bot arenas. |
| D3 | AI twins are **spec-only until their model feature is `passing`**. PhoBERT twins stay blocked until F301 is `passing`. | Rule B2 (signal before infrastructure) and F201 -> F301 dependency. |

## 1. Preconditions
1. `./init.sh` passes clean.
2. Read progress files, `DECISIONS.md`, and `architecture.md`.
3. Check F203 regime gating dependencies.
4. Resolve report inconsistencies before citing figures.
5. WIP=1: F501 is the active feature.

## 2. Feature Specification
- **ID:** F501
- **Name:** Multi-bot strategy arena: registry + Monte Carlo microstructure simulator
- **Behavior:** 300+ composite bots (strategy components S01-S26 plus AI twins) run on stationary-block-bootstrap paths under VN microstructure (T+2.5 lock, price limits, fees/tax/slippage, 25% NAV cap). Reports distribution metrics, effective-N-deflated Sharpe, CVaR95, MaxDD, PBO, and head-to-head matrix. Strictly simulation: zero broker code (Rule B1).

## 3. File Tree
```
src/arena/
  __init__.py
  bot_registry.py      # M1: Component registry and bot combinations
  bots.py              # M3: Bot protocol + component evaluators
  microstructure.py    # M2: Settlement lock, price limits, costs, NAV cap
  scenarios.py         # M4: 5 situations + stationary block bootstrap
  stats.py             # M5: DSR, CVaR, MaxDD, PBO, H2H matrix
  run.py               # M6: CLI orchestrator
configs/arena.yaml     # Microstructure and simulator assumptions
tests/
  test_bot_registry.py
  test_arena_microstructure.py
  test_arena_stats.py
```
