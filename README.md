# VESTA — Vietnamese Equity Sentiment-Triggered Agent

**Repo:** [Azure06072005/VESTA](https://github.com/Azure06072005/VESTA)
**Related repos:** [HybridACD](https://github.com/Azure06072005/HybridACD) · [braintodo](https://github.com/Azure06072005/braintodo)

VESTA is a research-first pipeline for the Vietnamese equity market. It scores
Vietnamese-language financial news for sentiment, cross-checks that signal
against fundamentals and market data with strict point-in-time correctness,
and — only after the underlying mean-reversion signal is proven statistically
— would consider any execution infrastructure. As of this writing the system
stops deliberately at "prove the signal and serve read-only inference"; the
execution layer is scaffolded but formally blocked pending a legal/compliance
gate, not an engineering one.

The build follows one non-negotiable ordering: **signal before infrastructure**.
No order-placement code, broker connectivity, or "just in case" scaffolding
gets built ahead of a backtested, reproducible edge.

---

## Unified research identity

VESTA is one of three repositories unified under a single thesis:

> **"Thiết Kế Mô Hình Tác Nhân Tự Lập Kế Hoạch cho Giao Dịch Tự Động Trong Thị
> Trường Chứng Khoán Việt Nam Dựa Vào Tín Hiệu Cảm Xúc Có Kiểm Chứng Tính Nhất
> Quán — Tích Hợp Mô Hình Ngôn Ngữ Nhỏ và Mô Hình Hành Động Lớn"**
> *(Designing a Self-Planning Agent Model for Autonomous Trading in the
> Vietnamese Equity Market Based on Consistency-Verified Sentiment Signals,
> Integrating Small Language Models and Large Action Models)*

| Repo | Role | What it does |
|---|---|---|
| **[VESTA](https://github.com/Azure06072005/VESTA)** | Data foundation | Crawlers, DuckDB pipeline, point-in-time joins, sentiment scoring, mean-reversion backtest |
| **[HybridACD](https://github.com/Azure06072005/HybridACD)** | Consistency layer | Consistency-checking module for LLM/SLM forecasters; filters unreliable sentiment signals before they reach a decision layer; written up as a Springer-LaTeX paper |
| **[braintodo](https://github.com/Azure06072005/braintodo)** | Planning layer | FastAPI/Uvicorn self-planning agent backend (deployable to Vercel); the top-level system that consumes consistency-verified sentiment as its input foundation |

Data flow: **VESTA (raw data → sentiment)** → **HybridACD (consistency
verification)** → **braintodo (planning agent, decision layer)**. Nothing
downstream is allowed to consume a signal that hasn't passed the layer above it.

---

## System architecture (VESTA)

```
vesta/
├── AGENTS.md / DECISIONS.md / conventions.md / architecture.md / verification.md
├── feature_list.json          single source of truth for what's done
├── claude-progress.md / gemini-progress.md   per-agent session logs
├── init.sh                    bootstrap: install → test → build → confirm
│
├── src/
│   ├── etl/                   db.py, retry_failed_jobs.py, migrations.py,
│   │                          news_dedup.py, batch_orchestrator.py, adjustments.py
│   ├── crawlers/
│   │   ├── dim_symbol.py          F001 — symbol master data
│   │   ├── cafef_symbol_directory.py  F001b — OTC/unlisted directory
│   │   ├── market_ohlcv.py        F002 — daily OHLCV
│   │   ├── vnstock_news.py        F003 — vnstock News module
│   │   ├── cafef_news.py          F004 — cafef.vn scraper (body text)
│   │   ├── fundamentals/          F005 — balance sheet / income / cash flow / ratio
│   │   ├── corporate_events.py    F006 — dividends, issuance, meetings
│   │   └── snapshots/             F007 — realtime quote (scope-reduced, see below)
│   ├── pipeline/
│   │   ├── validate_crossref.py   F101 — cross-dataset referential integrity
│   │   ├── pit_join.py            F102 — point-in-time news+price+fundamental join
│   │   └── backtest_meanreversion.py  F201 — the proof backtest
│   ├── models/                    F301/F302 — PhoBERT-base fine-tune (gated on F201)
│   ├── service/                   F401/F402 — read-only inference + feedback log
│   └── execution/                 F901/F902 — BLOCKED, stub only
│
├── configs/                   DuckDB schema, ticker universe, model hyperparams
├── data/                      local Parquet lake (gitignored)
├── out/                       backtest/eval reports (gitignored except fixtures)
└── tests/                     mirrors src/ 1:1
```

Database: DuckDB with `staging` / `core` / `meta` schemas. `meta.crawl_progress`
backs a resumable batch orchestrator across the ~1,751-symbol universe.

---

## Current status by tier

### ✅ Tier F0xx — Data crawlers & ETL (COMPLETE, 10/10 passing)

| Feature | What it proved |
|---|---|
| F000 | DuckDB staging/core/meta schemas bootstrapped, dependencies pinned |
| F001 | 1,751 symbols in `core.dim_symbol`; `is_delisted` derived from vnstock's real `exchange='DELISTED'` signal |
| F001b | Cafef OTC/unlisted directory — 984 rows, 6-way instrument-type classifier, explicit allowlists (no keyword heuristics) |
| F002 | Full-universe OHLCV crawl: 1,689 success / 62 empty / 0 failed across 1,751 symbols (~2.3M rows) |
| F003 | vnstock `Company.news()` confirmed to return **only disclosure notices, no body text** — not viable as a body-text source |
| F004 | cafef.vn confirmed as the real body-text source (`div.detail-content`); pagination endpoint confirmed via `.har` capture |
| F005 | Fundamentals crawler; pivoted-schema melt logic; `balance_sheet` empty-response accepted as a real, documented API gap |
| F006 | Corporate events; confirmed closed-set category field; full history by default |
| F007 | Realtime quote only — original 5-sub-type scope was found to be **fabricated evidence** and formally reverted (see incidents below) |
| F008 | Retry/reconciliation module distinguishing transient failure from genuine API emptiness |
| F009 | Tier checkpoint: fresh re-verification of F000–F008, fixed a look-ahead-bias leak in fundamentals revisions, added corporate-action adjustment, news dedup, and a resumable batch orchestrator |

### ✅ Tier F1xx — Validation & point-in-time join (COMPLETE, 2/2 passing)

- **F101** — cross-dataset referential integrity (orphan symbols, future timestamps, orphan adjustment events all fail loudly).
- **F102** — the single most important look-ahead-bias gate in the repo: joins news (deduped), OHLCV (adjusted, not raw), and fundamentals (via `get_as_of()`, correctly time-gated) into `core.pit_events`. Explicit tests prove post-close news isn't joined same-day, and a restatement fetched later doesn't leak backward.

### 🔧 Tier F2xx — Proof backtest (IN PROGRESS)

- **F201** — cheap rule-based sentiment scorer (hand-built Vietnamese financial lexicon, explicitly flagged as unsourced) + `backtest_meanreversion.py` (paired t-test, per-regime breakdown, Cohen's d, `MIN_SAMPLE_SIZE=10` honesty gate). Real F102→F201 DuckDB integration verified end-to-end.
- Test suite: **191 passed / 1 xfailed** (the xfail is an intentional, documented survivorship-bias placeholder).
- **Blocking items before F201 fully closes / F005–F007 can reopen for the full-universe run:**
  1. Confirm the F004c `extract_symbol()` contamination DELETE with real pasted stdout (~39K rows affected by a bare-word regex matching non-ticker strings like "CEO", "HCM", "USD").
  2. Redesign `extract_symbol()` with explicit negative test cases covering that exact failure mode.

### ⛔ Tier F3xx/F4xx — Model layer & deployment (NOT STARTED, gated)

F301 (PhoBERT-base fine-tune) and F302 (re-run backtest on SLM scores) do not start until F201 shows a statistically significant effect. F401/F402 (read-only inference service + feedback log) follow after.

### ⛔ Tier F9xx — Execution (BLOCKED — legal gate, not engineering)

F901 (broker compliance confirmation) and F902 (sandbox paper trading) remain blocked. This is treated as a document/correspondence requirement, not something resolved by writing code.

---

## Key incidents & what they taught

- **F007 fabricated evidence (2026-08-16).** A prior session's evidence field claimed 5 snapshot sub-types with per-type retention policies. Direct repo inspection found no matching code and no matching `DECISIONS.md` entry. Reverted to the real, verified scope (realtime quote only). This is why the project's standing rule is **"confirmed means pasted stdout"** — session narratives, even from a prior AI agent, are treated as unverified claims until checked against a real artifact.
- **F004c symbol-extraction contamination.** `extract_symbol()`'s bare-word regex matched common non-ticker strings against the real ticker universe, contaminating ~39K news rows. A 6-test suite passed the whole time — it only validated the positive path and had a blind spot at exactly the failure mode that mattered. Lesson: passing tests are insufficient evidence when the suite doesn't cover the specific failure mode in question.
- **Look-ahead bias in fundamentals (F009).** Financial statement restatements were silently overwriting original values. Fixed with an append-only, `fetched_at`-keyed primary key and two explicit vintage-selection functions: `get_as_reported()` (safe default for backtesting) and `get_as_of()` (current-belief queries, never for backtesting).
- **dim_symbol contamination from version drift.** 1,469 bond rows and 14 index-fund rows previously leaked in via keyword heuristics — fixed with explicit allowlists verified against the real cafef directory.

---

## Guiding principles

1. **WIP = 1.** One feature open at a time; a feature's blocking items must be resolved with evidence before the next one starts.
2. **"Confirmed means pasted stdout."** No diagnostic claim, fix, or crawl result is accepted without real terminal output.
3. **Look-ahead bias is a first-class concern**, verified structurally (point-in-time joins, revision-safe fundamentals), never assumed away.
4. **Numbers need a source.** No unsourced benchmark, accuracy figure, or backtest statistic is presented as fact — see `DISCLOSURE_LAG_DAYS=30`, sourced to Circular 96/2020/TT-BTC plus a documented HOSE extension-request pattern, replacing an earlier unsourced 45-day guess.
5. **Signal before infrastructure.** The execution layer stays blocked until both a proven backtest signal (F201/F302) and a written compliance confirmation (F901) exist.
6. **Raw-payload-preserving crawlers.** Any crawler with a wide/unstable schema (fundamentals, corporate events, snapshots) stores the full raw response as JSON alongside typed columns, so future schema drift doesn't require a backfill.

---

## Tooling & data sources

- **Stack:** Python, DuckDB (staging/core/meta), `vnstock==4.0.5`, `vnstock_data==3.2.7` (paid, surface unverified), pandas, pyarrow, requests, BeautifulSoup4, pytest, ruff, mypy.
- **Data sources:** vnstock community API (market data, some news metadata), cafef.vn (article body text, company directory, category pagination), vnstock_data (Insights/Analytics/Macro — installed but not yet live-verified).
- **No CI/CD** — manual push by the project owner; verification is done per-session against `verification.md`'s copy-pasteable commands (install → tests → lint → type-check → smoke run).

---

## What's next

1. Confirm the F004c contamination DELETE with real pasted stdout and redesign `extract_symbol()`'s negative test coverage.
2. Reopen F005/F006/F007 for the full ~1,751-symbol universe crawl (currently only OHLCV is fully crawled at scale).
3. Close out F201 with a real statistical verdict on the mean-reversion hypothesis, per-regime.
4. If F201 is significant: fine-tune PhoBERT-base (F301) and re-run the backtest with SLM scores (F302).
5. Wire HybridACD's consistency-verification step into the sentiment pipeline ahead of any decision layer.
6. Connect verified signals to braintodo's planning-agent backend via a read-only inference service (F401) — no order logic, ever, until F901 is resolved.
