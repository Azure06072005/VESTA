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
    - **F006 (Corporate Events)**: `discover_corporate_events_schema.py` WAS run against the live vnstock API on 2026-08-13.
      - **Output details:**
        ```text
        columns: ['id', 'event_name_vi', 'event_name_en', 'ticker', 'event_code', 'event_title_vi', 'event_title_en', 'display_date1', 'public_date', 'exercise_ratio', 'category', 'display_date2', 'start_date', 'end_date', 'action_type_vi', 'action_type_en', 'record_date', 'exright_date', 'payout_date', 'value_per_share', 'issue_date', 'listing_date']
        dtypes:
         id                  object
        event_name_vi       object
        event_name_en       object
        ticker              object
        event_code          object
        event_title_vi      object
        event_title_en      object
        display_date1       object
        public_date         object
        exercise_ratio     float64
        category            object
        display_date2       object
        start_date          object
        end_date            object
        action_type_vi      object
        action_type_en      object
        record_date         object
        exright_date        object
        payout_date         object
        value_per_share    float64
        issue_date          object
        listing_date        object
        dtype: object
        row count: 50
        
        unique event_type-ish values:
          event_name_vi: ['Giao dịch nội bộ: Giao dịch cá nhân', 'Giao dịch nội bộ: Giao dịch người liên quan', 'Giao dịch nội bộ: Giao dịch tổ chức', 'Niêm yết thêm', 'Phát hành cổ phiếu', 'Trả cổ tức bằng tiền mặt', 'Đại hội Đồng Cổ đông']
          event_name_en: ['Additional Listing', 'Annual General Meeting', 'Cash Dividend', 'Director Deal: Individual transactions', 'Director Deal: Institutional transactions', 'Director Deal: Related Person transactions', 'Share Issue']
          event_code: ['AGME', 'AIS', 'DDIND', 'DDINS', 'DDRP', 'DIV', 'ISS']
          category: ['DIVIDEND', 'MAJOR_SHAREHOLDER_TRADING', 'OTHER', 'SHAREHOLDER_MEETING']
        ```
      - **Conclusion**: The `.events()` endpoint returns 22 columns. The `event_type` can be mapped from `event_code` or `category`. It seems to return history all at once (50 rows spanning multiple years), so "chunked per-year" may not be required!

## Session 2 — 2026-08-14
- Completed: F004 (cafef.vn news crawler / secondary news scraper) — built, tested, and verified live.
- Verification Details & Test Suite:
  - Added dependencies to `requirements.txt`: `beautifulsoup4>=4.12.0`, `requests>=2.32.0`, `types-requests>=2.32.0`.
  - **Unit Tests**: 8/8 tests passed in `tests/test_cafef_crawler.py`.
  - **Full Suite**: 58 passed, 1 xfailed (known delisted_date gap in F001):
    ```text
    ============================= test session starts =============================
    platform win32 -- Python 3.12.10, pytest-8.3.3, pluggy-1.6.0 -- D:\VESTA\.venv\Scripts\python.exe
    rootdir: D:\VESTA
    collected 59 items

    tests/test_cafef_crawler.py ........                                     [ 13%]
    tests/test_corporate_events.py ..........                                [ 30%]
    tests/test_db_bootstrap.py ...                                           [ 35%]
    tests/test_dim_symbol.py ......x                                         [ 47%]
    tests/test_fundamental_crawler.py .........                              [ 62%]
    tests/test_market_crawler.py .......                                     [ 74%]
    tests/test_retry_module.py .......                                       [ 86%]
    tests/test_vnstock_news_crawler.py ........                              [ 100%]

    ======================== 58 passed, 1 xfailed in 2.07s ========================
    ```
  - **Linter & Type Checking**:
    - `ruff check src tests`: All checks passed!
    - `mypy src/crawlers/cafef_news.py tests/test_cafef_crawler.py --ignore-missing-imports`: Success (0 issues).
  - **Live Scraper Execution**:
    - Target symbols: `FPT`, `VNM`.
    - Live fetch executed against `https://cafef.vn/du-lieu/tin-doanh-nghiep/{symbol}/Event.chn`.
    - `robots.txt` live check passed (`Allow: /` confirmed at runtime).
    - `FPT`: wrote 3 rows to `staging.news` and `core.news`.
    - `VNM`: wrote 3 rows to `staging.news` and `core.news`.
    - **Live Idempotency Verified**: Second run on `FPT` wrote 3 rows with `DELETE ... WHERE source_url IN ?` dedup; total row count in `core.news` for `(symbol='FPT', source='cafef')` remained exactly 3.
  - **Live Sample Data from DuckDB**:
    ```json
    [
      {
        "symbol": "FPT",
        "source": "cafef",
        "published_at": "2026-08-05T12:07:00.000",
        "available_at": "2026-08-05T12:07:00.000",
        "headline": "Hơn 6.400 nhân sự rời khỏi báo cáo của 8 ngân hàng, 14 DN đứng đầu đã giảm 21.730 lao động",
        "body": null,
        "source_url": "https://cafef.vn/FPT-2946651/hon-6400-nhan-su-roi-khoi-bao-cao-cua-8-ngan-hang-14-dn-dung-dau-da-giam-21730-lao-dong.chn",
        "fetched_at": "2026-08-14 05:27:57.634"
      },
      {
        "symbol": "FPT",
        "source": "cafef",
        "published_at": "2026-08-04T09:18:00.000",
        "available_at": "2026-08-04T09:18:00.000",
        "headline": "Khi các 'ông lớn' bắt đầu tuyển dụng trở lại: Thế Giới Di Động, Vinhomes dẫn đầu nhóm 13 DN tuyển thêm 11.500 lao động, 4 ngân hàng tăng 2.500 người",
        "body": null,
        "source_url": "https://cafef.vn/FPT-2946179/khi-cac-ong-lon-bat-dau-tuyen-dung-tro-lai-the-gioi-di-dong-vinhomes-dan-dau-nhom-13-dn-tuyen-them-11500-lao-dong-4-ngan-hang-tang-2500-nguoi.chn",
        "fetched_at": "2026-08-14 05:27:57.634"
      },
      {
        "symbol": "FPT",
        "source": "cafef",
        "published_at": "2026-08-04T08:03:00.000",
        "available_at": "2026-08-04T08:03:00.000",
        "headline": "FPT sắp phát hành hơn 171 triệu cổ phiếu thưởng cho cổ đông",
        "body": null,
        "source_url": "https://cafef.vn/FPT-2946679/fpt-sap-phat-hanh-hon-171-trieu-co-phieu-thuong-cho-co-dong.chn",
        "fetched_at": "2026-08-14 05:27:57.634"
      }
    ]
    ```
- Status in `feature_list.json`: F004 marked `passing`.
- In progress: F007 (Insights/Analytics snapshot crawler + retention policy decision).
- Blocked: None for data tier (F901/F902 remain blocked on compliance/paper-trading gate).
- Next session should: Formulate retention policy for F007 in `DECISIONS.md` (accumulate daily vs overwrite latest per snapshot type) and implement F007 crawler suite.

## Session 3 — 2026-08-21
- Completed: F101 (Cross-dataset validation gate) — built `src/pipeline/validate_crossref.py` and `tests/test_crossref_validation.py`. Fails loudly with `ValidationError` on orphan symbols, future timestamps, and orphan adjustment events.
- Completed: Crawler `run()` signature fixes for orchestrator compatibility (`market_ohlcv.py`, `fundamentals.py`, `snapshots.py`).
- Completed: Created `scratch/export_symbols.py` (exports 3,442 symbols to plain text file).
- Verification: 108 passed, 1 xfailed (full test suite, 109 collected); `ruff` clean; `mypy` clean on 31 source files.
- Status in `feature_list.json`: F101 marked `passing`.
- Next session should: Implement F102 (Point-in-time news+price+fundamental join) — `src/pipeline/pit_join.py` and `tests/test_pit_join.py`.

## Session 4 — 2026-08-22
- Completed: F102 (Point-in-time news+price+fundamental join) — added `staging.pit_events` and `core.pit_events` to `configs/duckdb_schema.sql`, implemented `src/pipeline/pit_join.py` and `tests/test_pit_join.py`.
- Verification: 13/13 passed (`test_pit_join.py`); 121 passed, 1 xfailed (full suite, 122 collected); `ruff` clean; `mypy` clean on 33 source files.
- Status in `feature_list.json`: F102 marked `passing`.
- Next session should: Implement F201 (PROOF: sentiment mean-reversion backtest on VN30).
