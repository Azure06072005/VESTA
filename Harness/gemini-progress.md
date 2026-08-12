# Progress Log (Gemini sessions)

Separate file from `claude-progress.md` so multiple agents don't clobber
each other's state (Isolation, per ACID Principles for Agent State). Same
format either way.

Note on role split for this project: Gemini (chat) is used for primary AI
research (data sourcing, statistical design, literature); Gemini Antigravity
is the primary coding agent and should treat this file as its main session
log when implementing features from `feature_list.json`. See DECISIONS.md
"Agent division of labor" entry.

## Session 0 — YYYY-MM-DD
- Completed: (nothing yet — harness scaffolding only, see
  claude-progress.md Session 1 for what was filled in on the docs side)
- In progress: —
- Blocked: —
- Next session should: run `./init.sh` (once `requirements.txt` exists —
  currently missing, this is likely the actual first task), check
  `feature_list.json` for an unclaimed feature (F001 is the natural start —
  see claude-progress.md), read `architecture.md` folder tree before
  creating any new file so it lands in the right module, and follow the
  same WIP=1 / verify-before-passing workflow as AGENTS.md regardless of
  which agent is running the session.

## Session 1 — 2026-08-11
- Completed: F001 (dim_symbol) — accepted limitation on delisted_date via DECISIONS.md.
- Completed: F002 (Market OHLCV daily crawler) — schema verified against live API (`time, open, high, low, close, volume`), tests passed, crawler executed successfully. Both marked as passing in feature_list.json.
  - **Test Output Detail (F001 & F002)**:
    ```text
    ============================= test session starts =============================
    platform win32 -- Python 3.12.10, pytest-8.3.3, pluggy-1.6.0
    rootdir: D:\VESTA
    collected 16 items

    tests\test_db_bootstrap.py ...                                           [ 18%]
    tests\test_dim_symbol.py ......x                                         [ 62%]
    tests\test_market_crawler.py ......                                      [100%]

    ======================== 15 passed, 1 xfailed in 2.50s ========================
    ```
  - **Data Testing Samples**:
    ```text
    === F001 dim_symbol Test Data ===
    
    Input Exchange DF:
      symbol          organ_name        en_organ_name exchange   type  id
    0    FPT            CTCP FPT             FPT Corp     HOSE  stock   1
    1    VNM       CTCP Vinamilk         Vinamilk JSC     HOSE  stock   2
    2    DPP  CTCP Dược Đồng Nai  Dong Nai Pharma JSC    UPCOM  stock   3
    
    Input Industry DF:
      symbol industry_code        industry_name
    0    FPT            11  Công nghệ thông tin
    1    VNM            22            Thực phẩm
    
    Output dim_symbol DF (joined & normalized):
      symbol          organ_name  ... delisted_date                 fetched_at
    0    FPT            CTCP FPT  ...           NaT 2026-08-12 04:58:47.500026
    1    VNM       CTCP Vinamilk  ...           NaT 2026-08-12 04:58:47.500026
    2    DPP  CTCP Dược Đồng Nai  ...           NaT 2026-08-12 04:58:47.500026
    
    === F002 market_ohlcv Test Data ===
    
    Input Raw OHLCV DF (synthetic):
            time  open  high   low  close   volume
    0 2024-01-02  93.4  94.0  93.0   93.9  1000000
    1 2024-01-03  94.4  95.0  94.0   94.9  1001000
    2 2024-01-04  95.4  96.0  95.0   95.9  1002000
    
    Output Normalized OHLCV DF:
      symbol        date  open  ...  close   volume                 fetched_at
    0    FPT  2024-01-02  93.4  ...   93.9  1000000 2026-08-12 04:58:47.510851
    1    FPT  2024-01-03  94.4  ...   94.9  1001000 2026-08-12 04:58:47.510851
    2    FPT  2024-01-04  95.4  ...   95.9  1002000 2026-08-12 04:58:47.510851
    ```
  - **Live API Verification Outputs (F002 & F005)**:
    - **F002 (Market OHLCV)**: `discover_ohlcv_schema.py` WAS run against the live vnstock API with my key. The columns returned were exactly `['time', 'open', 'high', 'low', 'close', 'volume']`. Therefore, `RAW_COLUMN_ALIASES` works as assumed.
    - **F005 (Fundamentals)**: `discorver_fundamentals_schema.py` was run against the live API. **CRITICAL ISSUE FOUND: MASSIVE SCHEMA DRIFT**. 
      - The `vnstock` API does NOT return one row per period with metrics as columns. 
      - It returns a pivoted shape where each financial item is a row (e.g. `1. Doanh thu bán hàng...`), and the columns are the periods (e.g. `2026-Q2`, `2026-Q1`). 
      - `balance_sheet` returned an empty DataFrame completely.
      - **Consequence for F005**: `PERIOD_END_ALIASES` will fail entirely because there is no `period_end` column. The crawler logic in `fundamentals.py` must be completely rewritten to melt (unpivot) the dataframe, map the period columns to a `period_end` column, and transpose the financial items into a JSON blob. 
      - **Decision Needed**: We need a formal `DECISIONS.md` entry confirming whether `DISCLOSURE_LAG_DAYS=45` is acceptable for `available_at` approximation, and how to handle the `balance_sheet` failure (empty API response). F005 cannot be marked passing until the crawler logic is rewritten to handle the pivoted data shape.
- In progress: F005 (Fundamental crawler suite) — rewriting required to handle pivoted schema.
- Blocked: F005 (Need decision on `DISCLOSURE_LAG_DAYS` and `balance_sheet` failure).
- Next session should: Rewrite F005 normalization logic using `pd.melt` to handle vnstock's pivoted fundamental schema, and resolve the open decisions.

<!--
Template for future entries:

## Session N — YYYY-MM-DD
- Completed: F0xx (name) — all tests passing, evidence: commit <hash>
- In progress: F0yy (name) — what's done, what's left
- Blocked: (dependency / decision needed, or "none")
- Next session should: <one concrete next action>
-->
