import json

file_path = "d:/VESTA/Harness/feature_list.json"
with open(file_path, "r", encoding="utf-8") as f:
    data = json.load(f)

comment_f05x = (
    "F05x tier added 2026-09-06 to retroactively track 21 crawlers + 2 support scripts built outside "
    "feature_list.json's ledger. This tier is AUXILIARY to the canonical F0xx pipeline -- F101/F102 do not "
    "depend on it and remain scoped to dim_symbol/market_ohlcv_daily/fundamentals/news only, per the "
    "2026-09-06 scope-boundary decision. Every feature below is 'active' (except F052 marked 'blocked'), "
    "not 'passing' -- code and a shared 339-test suite exist and collectively pass, but no INDIVIDUAL "
    "feature has been separately live-verified (real endpoint confirmed, live row count pasted) the way "
    "F001-F009 originally were. Do not treat 'active' here as equivalent to a from-scratch passing verification."
)

data["_comment_f05x_tier"] = comment_f05x

f05x_features = [
    {
        "id": "F050",
        "name": "cafef.vn market index daily crawler (market_index_daily)",
        "behavior": "VNINDEX/HNX-INDEX/UPCOM-INDEX daily OHLCV via cafef_data_market.py.",
        "dependencies": ["F001"],
        "verification": "pytest tests/test_cafef_data_market.py -x",
        "state": "active",
        "evidence": "Code + tests exist, part of the 339-pass suite. NOT individually re-verified against a fresh live pull -- pending."
    },
    {
        "id": "F051",
        "name": "cafef.vn foreign investor flow crawler (market_foreign_flow_daily)",
        "behavior": "Daily foreign buy/sell volume and foreign room per symbol via cafef_foreign_flow.py. Volume-only schema per rules B3/B4 (fabricated buy_value/sell_value/net_value columns dropped).",
        "dependencies": ["F001"],
        "verification": "pytest tests/test_cafef_foreign_flow.py -x",
        "state": "active",
        "evidence": "Code + tests exist. Verified against raw CafeF CCNN AmiBroker export: feed is volume-only (<Open>/<High>/<OI>), monetary values were 0.0 placeholders. Updated to volume-only; 2/2 tests pass."
    },
    {
        "id": "F052",
        "name": "cafef.vn BCTC financial-statement enhancer -- balance_sheet gap fix",
        "behavior": "REVERSES the 2026-08-12 accepted gap (vnstock_data's balance_sheet() returns empty). Uses apiweb.cafef.vn/api/v2/BCTC (GetReportCDKT/GetReportDetail/GetReportLCTT/FinancialIndicators) -- the SAME endpoint this project independently verified live on 2026-08-31/09-02 (Origin/Referer headers required, confirmed real). Writes into the EXISTING core.fundamentals table alongside vnstock_data-sourced rows.",
        "dependencies": ["F005"],
        "verification": "pytest tests/test_cafef_finance_enhancer.py -x",
        "state": "blocked",
        "evidence": "Code + tests exist. MARKED BLOCKED pending completion of full schema normalization / downstream adapter: although source column was added to core.fundamentals (distinguishing vnstock_data from cafef) and get_as_of() now safely filters/selects source, cafef's raw Vietnamese line-item key payload differs from vnstock_data's standardized English codes and balance_sheet remains 100% cafef-sourced."
    },
    {
        "id": "F053",
        "name": "Batch equity enhancer -- fundamentals/corporate_events gap-fill orchestrator",
        "behavior": "Backfills core.fundamentals/core.corporate_events for symbols prioritized by 2026 liquidity (VN30/Large/Mid cap). Orchestration utility over F005/F006/F052, not a new primary data source.",
        "dependencies": ["F052", "F006"],
        "verification": "pytest tests/test_batch_equity_enhancer.py -x",
        "state": "active",
        "evidence": "Code + tests exist."
    },
    {
        "id": "F054",
        "name": "Vietstock Finance equity research report crawler (core.stock_research_reports)",
        "behavior": "Broker recommendations/target prices/PDF reports from finance.vietstock.vn. NEW TABLE, not previously scoped anywhere in feature_list.json.",
        "dependencies": ["F001"],
        "verification": "pytest tests/test_vietstock_finance_enhancer.py -x",
        "state": "active",
        "evidence": "Code + tests exist."
    },
    {
        "id": "F055",
        "name": "Vietstock general macro/market news crawler (core.macro_policy)",
        "behavior": "News/macro/banking/commodities/derivatives/bonds from vietstock.vn via ChannelContentPage pagination.",
        "dependencies": ["F001"],
        "verification": "pytest tests/test_vietstock_crawler.py -x",
        "state": "active",
        "evidence": "Code + tests exist."
    },
    {
        "id": "F056",
        "name": "World Bank Open Data macro indicator crawler",
        "behavior": "Vietnam macro indicators via World Bank's public REST API.",
        "dependencies": [],
        "verification": "pytest tests/test_worldbank_crawler.py -x",
        "state": "active",
        "evidence": "Code + tests exist."
    },
    {
        "id": "F057",
        "name": "SBV (State Bank of Vietnam) monetary policy crawler",
        "behavior": "Press releases, policy rate decisions, circulars from sbv.gov.vn.",
        "dependencies": [],
        "verification": "pytest tests/test_sbv_crawler.py -x",
        "state": "active",
        "evidence": "Code + tests exist."
    },
    {
        "id": "F058",
        "name": "Báo Chính phủ regulatory/macro crawler",
        "behavior": "Government directives, PM decisions from baochinhphu.vn.",
        "dependencies": [],
        "verification": "pytest tests/test_baochinhphu_crawler.py -x",
        "state": "active",
        "evidence": "Code + tests exist."
    },
    {
        "id": "F059",
        "name": "SSC (State Securities Commission) enforcement/regulation crawler",
        "behavior": "Sanctions, market supervision, issuance approvals from ssc.gov.vn.",
        "dependencies": [],
        "verification": "pytest tests/test_ssc_crawler.py -x",
        "state": "active",
        "evidence": "Code + tests exist."
    },
    {
        "id": "F060",
        "name": "VnEconomy macro/industry policy crawler",
        "behavior": "Macro/finance/real-estate/digital-economy news, robots.txt Crawl-delay:1.0s respected.",
        "dependencies": [],
        "verification": "pytest tests/test_vneconomy_crawler.py -x",
        "state": "active",
        "evidence": "Code + tests exist."
    },
    {
        "id": "F061",
        "name": "Tin Nhanh Chung Khoan crawler",
        "behavior": "Listed-company news, dividend rights, AGMs, expert commentary.",
        "dependencies": [],
        "verification": "pytest tests/test_tinnhanhchungkhoan_crawler.py -x",
        "state": "active",
        "evidence": "Code + tests exist."
    },
    {
        "id": "F062",
        "name": "Bao Dau Tu crawler",
        "behavior": "Securities/banking/enterprise/public-investment/real-estate news (Ministry of Planning & Investment organ).",
        "dependencies": [],
        "verification": "pytest tests/test_baodautu_crawler.py -x",
        "state": "active",
        "evidence": "Code + tests exist."
    },
    {
        "id": "F063",
        "name": "Thoi Bao Ngan Hang crawler",
        "behavior": "Monetary market/rates/FX/SBV policy news via infinite-scroll pagination.",
        "dependencies": [],
        "verification": "pytest tests/test_thoibaonganhang_crawler.py -x",
        "state": "active",
        "evidence": "Code + tests exist."
    },
    {
        "id": "F064",
        "name": "VINAPRINT (printing association) sector policy crawler",
        "behavior": "Regulations affecting packaging/paper-product tickers (DHC, HHP, GDT, SVI).",
        "dependencies": [],
        "verification": "pytest tests/test_vinaprint_crawler.py -x",
        "state": "active",
        "evidence": "Code + tests exist."
    },
    {
        "id": "F065",
        "name": "VBA (beverage association) sector policy crawler",
        "behavior": "Excise-tax/labeling/EPR policy affecting SAB/BHN/MSN.",
        "dependencies": [],
        "verification": "pytest tests/test_vba_crawler.py -x",
        "state": "active",
        "evidence": "Code + tests exist."
    },
    {
        "id": "F066",
        "name": "NDA (national data association) tech-policy crawler",
        "behavior": "Data-infrastructure/cloud policy affecting FPT/CTR/ELC/CMG/ITD.",
        "dependencies": [],
        "verification": "pytest tests/test_nda_crawler.py -x",
        "state": "active",
        "evidence": "Code + tests exist."
    },
    {
        "id": "F067",
        "name": "Hoi Nong Dan (farmers association) agri-policy crawler",
        "behavior": "Fertilizer/agri-input/export policy affecting DPM/DCM/BFC/PAN/LTG/HAG/TAR.",
        "dependencies": [],
        "verification": "pytest tests/test_hoinongdan_crawler.py -x",
        "state": "active",
        "evidence": "Code + tests exist."
    },
    {
        "id": "F068",
        "name": "MOIT (Ministry of Industry & Trade) energy/trade policy crawler",
        "behavior": "Fuel-price administration, power pricing, trade-defense policy affecting POW/GAS/PLX/OIL/BSR/HPG/HSG/PC1/GEG.",
        "dependencies": [],
        "verification": "pytest tests/test_moit_crawler.py -x",
        "state": "active",
        "evidence": "Code + tests exist."
    },
    {
        "id": "F069",
        "name": "VITA (tourism association) sector policy crawler",
        "behavior": "Visa/tourism-recovery policy affecting HVN/VJC/SKG/DAH/VTD.",
        "dependencies": [],
        "verification": "pytest tests/test_vita_crawler.py -x",
        "state": "active",
        "evidence": "Code + tests exist."
    },
    {
        "id": "F070",
        "name": "VASEP (seafood export association) crawler",
        "behavior": "Seafood export/tariff/IUU-yellow-card data.",
        "dependencies": [],
        "verification": "pytest tests/test_vasep_crawler.py -x",
        "state": "active",
        "evidence": "Code + tests exist."
    },
    {
        "id": "F071",
        "name": "HoREA (HCMC real-estate association) regulatory crawler",
        "behavior": "Land-law/housing-law reform petitions affecting real-estate tickers.",
        "dependencies": [],
        "verification": "pytest tests/test_horea_crawler.py -x",
        "state": "active",
        "evidence": "Code + tests exist."
    },
    {
        "id": "F072",
        "name": "TIER CHECKPOINT: F05x auxiliary-data audit gate",
        "behavior": "Mirrors F009's role for this new tier: re-verify F050-F071 with FRESH live evidence (not the aggregate 339-pass count), confirm no table/schema collisions with the canonical F0xx tables, and formally decide whether/how F102 should ever consume core.macro_policy/core.stock_research_reports (not assumed -- a real scoping decision). F101/F102 do NOT depend on this gate.",
        "dependencies": [
            "F050","F051","F052","F053","F054","F055","F056","F057","F058","F059",
            "F060","F061","F062","F063","F064","F065","F066","F067","F068","F069",
            "F070","F071"
        ],
        "verification": "Individual live-evidence pass per feature, not just aggregate pytest -- see AGENTS.md Session Lifecycle and this project's 'confirmed means pasted stdout' standard.",
        "state": "not_started",
        "evidence": None
    }
]

# Insert F050-F072 right after F009
features = data["features"]
f009_idx = next(i for i, f in enumerate(features) if f["id"] == "F009")

# Filter out any pre-existing F05x if re-running
features = [f for f in features if not (f["id"].startswith("F05") or f["id"].startswith("F06") or f["id"].startswith("F07"))]
f009_idx = next(i for i, f in enumerate(features) if f["id"] == "F009")

features[f009_idx+1:f009_idx+1] = f05x_features
data["features"] = features

with open(file_path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print("Updated feature_list.json successfully. Total features:", len(features))
