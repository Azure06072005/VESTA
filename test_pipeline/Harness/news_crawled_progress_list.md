# News Crawled Progress List & Gap Analysis — VESTA

**Last Updated**: 2026-09-11  
**Harness Location**: `Harness/news_crawled_progress_list.md`  
**Canonical Datasets**: `db/vesta.duckdb` & `db/vesta_latest_backup.duckdb`  
**Total Ingested Articles**: **939,732 articles** (661,558 in `core.news` + 278,174 in `core.macro_policy`)  
**Total Crawled Sources**: **51 active sources** | **Uncrawled / Pending Sources**: **16 sources**

---

## 1. Master Progress Table: Crawled Sites & Status

### A. Company-Specific Equity News (`core.news` — 661,558 Articles)
| # | Source Key | Publisher / Portal | Category | Total Articles | Date Range Covered | Body Fill Rate | Status & Notes |
| :-: | :--- | :--- | :--- | :-: | :---: | :-: | :--- |
| 1 | `cafef` | CafeF Financial Portal | Equities & Disclosure | **587,995** | 2007-02-23 to 2026-09-07 | 0.01% (38 bodies) | **Headline Crawl Complete**; Body enrichment via `src/crawlers/cafef_article_body.py` needed for full text. |
| 2 | `vnstock` | vnstock_news API | Corporate Disclosures | **73,563** | 2016-10-27 to 2026-08-27 | **100.0%** (73,563 bodies) | **Fully Complete** with full article text. |

---

### B. Macroeconomic, Regulatory & Sectoral News (`core.macro_policy` — 278,174 Articles across 51 Sources)

#### 1. Government Ministries & Regulatory Authorities
| # | Source Key | Agency / Portal | Total Articles | Date Range | Body Fill Rate | Coverage & Gap Status |
| :-: | :--- | :--- | :--- | :-: | :---: | :-: | :--- |
| 1 | `baochinhphu` | Báo Điện tử Chính phủ | **36,047** | 2009-08-29 to 2026-09-07 | **100.0%** | **Strong Coverage** (Prime Ministerial decisions, decrees). Gap: 2000–2008. |
| 2 | `ssc` | Ủy ban Chứng khoán Nhà nước | **2,861** | 2004-10-13 to 2026-09-03 | **100.0%** | **Deep History** back to 2004 (securities violations, public filings). |
| 3 | `moit` | Bộ Công Thương | **82** | 2021-09-13 to 2026-09-04 | **100.0%** | **Partial**. Only recent trade & energy policy. Needs historical crawl. |
| 4 | `mof` | Bộ Tài chính (mof.gov.vn) | **1,566** | 2009-05-06 to 2026-09-09 | **100.0%** | **ACTIVE & VERIFIED**. High-speed REST API crawler (`deep_portal_crawler.py`) across 12 ministerial policy categories with full HTML/plain text bodies. 17-year archive reached. |
| 5 | `gdt` | Tổng cục Thuế (gdt.gov.vn) | **35** | 2025 to 2026 | **100.0%** | **ACTIVE**. Crawled from `tin-tuc.har` with full circular/directive body text. IBM WebSphere portal designated for user HAR captures. |
| 6 | `moj` | Bộ Tư pháp | **56** | 2026-09-07 to 2026-09-07 | **100.0%** | **Probe Batch**. Legal appraisal gazettes. |
| 7 | `sbv` | Ngân hàng Nhà nước (SBV) | **3** | 2026-09-03 to 2026-09-03 | **100.0%** | **CRITICAL GAP**. Only 3 sample items. Needs full archive crawl (`.har` recommended). |

#### 2. Financial Media & Business Press
| # | Source Key | Media Entity | Total Articles | Date Range | Body Fill Rate | Coverage & Gap Status |
| :-: | :--- | :--- | :--- | :-: | :---: | :-: | :--- |
| 8 | `tinnhanhchungkhoan` | Tin Nhanh Chứng Khoán | **102,344** | 2022-01-04 to 2026-09-11 | **100.0%** | **MASSIVE HISTORICAL ARCHIVE**. Sitemaps swept across 2022–2026; 100% full body & UTC timestamps. Next resume: 2021. |
| 9 | `vietstock` | Vietstock Portal | **15,893** | 2025 to 2026 | **100.0%** | **ACTIVE**. Ingested from 14 HAR archives (insider trades, macro data, disclosures). |
| 10 | `baodautu` | Báo Đầu tư (MPI) | **15,804** | 2026-09-05 to 2026-09-05 | **100.0%** | **Large Volume**. Needs date backfill (dates stamped on ingestion). |
| 11 | `thoibaonganhang` | Thời báo Ngân hàng | **11,748** | 2026-09-05 to 2026-09-05 | **100.0%** | **High Volume**. Banking & monetary credit articles. |
| 12 | `vneconomy` | VnEconomy | **2,248** | 2021 to 2026 | **100.0%** | **ACTIVE**. 14 HAR files ingested (stocks, property, digital economy, market). |
| 13 | `vietnamfinance` | VietnamFinance | **1,155** | 2026 | **100.0%** | **ACTIVE**. 13 HAR archives ingested (banking, corporate debt, investment). |
| 14 | `thoibaotaichinh` | Thời báo Tài chính VN | **78** | 2026-09-07 to 2026-09-07 | **100.0%** | **Sample Batch**. Fiscal & public debt policy. |
| 15 | `vnanet` | TTXVN (VNA) | **26** | 2026-09-07 to 2026-09-07 | **100.0%** | **Sample Batch**. Official state economic wires. |
| 16 | `tcct` | Tạp chí Công Thương | **10** | 2026-09-07 to 2026-09-07 | **100.0%** | **Sample Batch**. Crawl-delay: 10s enforced. |
| 17 | `nguoiquansat` | Người Quan Sát | **10** | 2026-09-07 to 2026-09-07 | **100.0%** | **Sample Batch**. 3,536 additional articles pending in HAR. |

#### 3. General National Newspapers (Financial / Market Sections)
| # | Source Key | Newspaper | Total Articles | Date Range | Body Fill Rate | Coverage & Gap Status |
| :-: | :--- | :--- | :--- | :-: | :---: | :-: | :--- |
| 18 | `tuoitre` | Báo Tuổi Trẻ | **63,058** | 2010-08-04 to 2026-09-10 | **100.0%** | **PAGES 1–1880 COMPLETED**. High-throughput timeline crawler (`tuoitre_crawler.py`) covering Zones 11, 89, 10, 3. Temporal boundary pushed to **2010-08-04** (16 continuous years). Next: Trang 1,881+. |
| 19 | `tienphong` | Báo Tiền Phong | **15,213** | 2025 to 2026 | **100.0%** | **MAX PAGES COMPLETED**. High-throughput JSON REST crawler reached backend cap (Page 250) across Zone 3 (Kinh tế), Zone 166 (Địa ốc), Zone 5 (Thế giới). |
| 20 | `nhandan` | Báo Nhân Dân | **10** | 2026-09-07 | **100.0%** | **Sample only**. 501 articles pending in HAR. |

#### 4. Industry Associations & Sector Bodies (29 Associations)
| # | Source Key | Association | Sector Focus | Articles | Date Range | Body Fill Rate |
| :-: | :--- | :--- | :--- | :-: | :---: | :-: |
| 19 | `vba` | Hiệp hội Bia - Rượu - NGK | Beverage & Consumer Goods | **1,513** | 2016 to 2026 | **100.0%** |
| 20 | `horea` | Hiệp hội BĐS TP.HCM | Property & Housing Decrees | **552** | 2015 to 2026 | **100.0%** |
| 21 | `nda` | Hiệp hội Dữ liệu Quốc gia | Digital Economy & IT | **517** | 2025 to 2026 | **100.0%** |
| 22 | `vita` | Hiệp hội Du lịch Việt Nam | Hospitality & Aviation | **190** | 2025 to 2026 | **100.0%** |
| 23 | `vinaprint` | Hiệp hội In Việt Nam | Packaging & Paper | **163** | Historical to 2026 | **100.0%** |
| 24 | `vnpca` | Hội Hóa chất Việt Nam | Fertilizers & Chemicals | **161** | 2026 | **100.0%** |
| 25 | `vasep` | Hiệp hội Thủy sản VASEP | Seafood Export Tariffs | **107** | 2026 | **100.0%** |
| 26 | `hoinongdan` | Hội Nông dân Việt Nam | Agri-business & Grains | **94** | 2019 to 2026 | **100.0%** |
| 27 | `vntextile` | Hiệp hội Dệt may (VITAS) | Garments & Cotton | **82** | 2026 | **100.0%** |
| 28 | `vsa` | Hiệp hội Thép Việt Nam | Steel & Construction | **24** | 2026 | **100.0%** |
| 29 | `vra` | Hiệp hội Cao su Việt Nam | Natural Rubber Equities | **23** | 2026 | **100.0%** |
| 30 | `vnba` | Hiệp hội Ngân hàng | Banking Regulations | **20** | 2026 | **100.0%** |
| 31 | `vla` | Hiệp hội Logistics (VLA) | Freight & Seaports | **12** | 2026 | **100.0%** |
| 32 | `hoidaukhi` | Hội Dầu khí Việt Nam | Energy Exploration | **12** | 2025 to 2026 | **100.0%** |
| 33 | `vecom` | Hiệp hội TMĐT (VECOM) | E-commerce | **8** | 2026 | **100.0%** |
| 34 | `via` | Hiệp hội Internet VN | Telecommunications | **8** | 2026 | **100.0%** |
| 35 | `avnuc` | Hội Doanh nghiệp Vừa & Nhỏ | SME Enterprises | **8** | 2017 | **100.0%** |
| 36 | `viea` | Viện Kinh tế Môi trường | ESG & Green Finance | **8** | 2026 | **100.0%** |
| 37 | `vacod` | Hiệp hội PT Kinh tế DN | Corporate Development | **8** | 2026 | **100.0%** |
| 38 | `vama` | Hiệp hội Ô tô (VAMA) | Automotive Industry | **8** | 2024 to 2026 | **100.0%** |
| 39 | `hhbvt` | Hiệp hội Bông Vải Sợi | Textile Materials | **8** | 2015 | **100.0%** |
| 40 | `vafie` | Hiệp hội DN ĐT Nước ngoài | FDI Capital Inflows | **8** | 2026 | **100.0%** |
| 41 | `vusta` | Liên hiệp các Hội KH-KT | Technical Standards | **7** | 2026 | **100.0%** |
| 42 | `luatvietnam` | Luật Việt Nam | Gazettes & Decrees | **7** | 2026 | **100.0%** |
| 43 | `huba` | Hiệp hội Doanh nghiệp TP.HCM| Regional Commerce | **5** | 2026 | **100.0%** |
| 44 | `thuvienphapluat`| Thư viện Pháp luật | Legal Records | **5** | Historical to 2026 | **100.0%** |
| 45 | `vpsaspice` | Hiệp hội Hồ tiêu VN | Spices & Exports | **4** | 2023 to 2026 | **100.0%** |
| 46 | `vfaea` | Hội Doanh nhân Lão thành | Economic Case Studies | **3** | 2026 | **100.0%** |
| 47 | `vinasme` | Hiệp hội DN Nhỏ & Vừa | SME Financing | **3** | 2026 | **100.0%** |

#### 5. Global Macroeconomic & Financial Indicators
| # | Source Key | Institution | Indicator / Topic | Articles | Temporal Range | Body Fill Rate | Status |
| :-: | :--- | :--- | :--- | :-: | :---: | :-: | :--- |
| 48 | `yahoo_finance` | Yahoo Finance Macro | Global rates, DXY, crude oil | **6,094** | 2013-09-12 to 2026-09-08 | **100.0%** | **Strong Depth** (13 years). |
| 49 | `worldbank` | World Bank Open Data | Vietnam macro aggregates | **219** | 1985-12-31 to 2025-12-31 | **100.0%** | **40-Year Time Series** (GDP, CPI). |

---

## 2. Rigorous Check Against User Requirements

### [Check 1] Ensure Data is Crawled in All Dates (2000 -> 2026)
- **Status**: **PARTIAL (Historical Gradient Gap)**.
- **Detailed Findings**:
  - `core.market_ohlcv_daily`: **100% complete from 2000-07-28 to 2026-09-04** (5,172,967 rows).
  - `core.news`: CafeF starts at **2007-02-23** (CafeF did not exist online before early 2007; digital archives prior to 2007 do not exist on the portal). vnstock covers **2016–2026**.
  - `core.macro_policy`: World Bank goes back to **1985**; UBCKNN (`ssc`) goes back to **2004**; Báo Chính phủ goes back to **2009**.
  - **Action Required**: For 2000–2006, general media archives do not exist online in Vietnam. We must crawl official archives from UBCKNN (`ssc.gov.vn`) and National Assembly/Government Gazettes (`thuvienphapluat.vn` / `luatvietnam.vn`). Furthermore, sources like `baodautu`, `vietstock`, and `thoibaonganhang` need deep pagination crawlers to backfill 2007–2024.

### [Check 2] Ensure Every Government Ministry & Regulatory Authority is Crawled
- **Status**: **INCOMPLETE (Key Ministries Missing)**.
- **Detailed Findings**:
  - Báo Chính phủ (36,047 articles) and UBCKNN (2,861 articles) are in place.
  - **Missing / Under-crawled**:
    - **NHNN (`sbv.gov.vn`)**: Only 3 articles. Must crawl monetary policy circulars, rediscount rate decisions, and reserve requirement announcements.
    - **Bộ Tài chính (`mof.gov.vn`)**: 0 articles (Pending crawler execution).
    - **Tổng cục Thuế (`gdt.gov.vn`)**: 0 articles (Pending crawler execution).
    - **Bộ Công Thương (`moit.gov.vn`)**: Only 82 articles.
    - **Sở GDCK Hà Nội (`hnx.vn`)** & **Sở GDCK TP.HCM (`hsx.vn`)**: Disclosures and market alerts not yet crawled.

### [Check 3] Ensure Financial Media & Business Press is Crawled
- **Status**: **STRONG ON HEADLINES, PARTIAL ON HISTORICAL ARCHIVES**.
- **Detailed Findings**:
  - 635,000+ financial media records exist across CafeF, Báo Đầu tư, Vietstock, Thời báo Ngân hàng, and VnEconomy.
  - However, except CafeF (2007–2026) and VnEconomy (2021–2026), several outlets only have recent items and require historical pagination scrapers.

### [Check 4] Ensure Industry Associations & Sector Bodies are Crawled
- **Status**: **BROAD BREADTH (29 BODIES), NARROW DEPTH**.
- **Detailed Findings**:
  - 29 associations are represented, but only 3 (`vba`, `horea`, `nda`) have $>500$ articles.
  - 26 associations have $<200$ articles (mostly recent front-page pulls). Needs full archive and dispatch category crawling.

### [Check 5] Ensure Other Newspapers (Tiền Phong, Tuổi Trẻ, Nhân Dân) are Crawled for Finance/Policy
- **Status**: **SAMPLE ONLY (CRITICAL BACKFILL NEEDED)**.
- **Detailed Findings**:
  - `tienphong`: 10 articles.
  - `tuoitre`: 8 articles.
  - `nhandan`: 10 articles.
  - These are currently only smoke-test samples. Dedicated section crawlers for `/kinh-te/`, `/tai-chinh/`, `/doanh-nghiep/` must be launched with full historical pagination.

### [Check 6] Ensure All Data Contains Full Body Content
- **Status**: **100% ON MACRO POLICY; 11% ON CORPORATE NEWS**.
- **Detailed Findings**:
  - `core.macro_policy`: **100.0% body fill rate** (all 95,461 articles contain full body text).
  - `core.news`: `vnstock` has **100% body text** (73,563 articles).
  - **The Giant Gap**: `cafef` in `core.news` has **587,957 articles missing full body text** (only 38 articles enriched). The enrichment crawler [`src/crawlers/cafef_article_body.py`](file:///d:/VESTA/src/crawlers/cafef_article_body.py) exists and must be run in background batch mode.

---

## 3. Which Sites Require `.har` Network Captures?

Standard HTTP libraries (`requests`/`urllib`) fail on certain portals due to Cloudflare WAF, anti-scraping JavaScript challenges, dynamic session tokens, or encrypted ASPX ViewStates.

To bypass these without building complex, brittle reverse-engineering layers, **you should capture `.har` files from your browser** (Open DevTools -> Network -> Preserve log -> Export HAR) for the following **6 critical sites**:

| # | Target Portal | Why a `.har` File is Strictly Required | What to Click in Browser Before Exporting `.har` |
| :-: | :--- | :--- | :--- |
| **1** | **Sở GDCK TP.HCM (`hsx.vn`)** | Direct Python requests return **HTTP 403 Forbidden** (Cloudflare/Akamai bot shield + dynamic cookie validation). | 1. Navigate to `https://www.hsx.vn/Modules/Listed/Web/SymbolView`<br>2. Filter announcements by a ticker (e.g. `VIC` or `VHM`)<br>3. Click Next Page (2, 3)<br>4. Save Network HAR. |
| **2** | **Sở GDCK Hà Nội (`hnx.vn`)** | ASPX WebForms architecture with encrypted `__VIEWSTATE`, `__EVENTVALIDATION`, and dynamic AJAX payloads for bond & equity disclosures. | 1. Go to `https://hnx.vn/vi-vn/thong-tin-cong-bo-doanh-nghiep.html`<br>2. Click on Corporate Bond announcements<br>3. Filter and paginate 2–3 pages<br>4. Save Network HAR. |
| **3** | **Vietstock Finance (`finance.vietstock.vn`)** | Heavy anti-bot shield with `__RequestVerificationToken`, encrypted session cookies, and rate-limit challenges on BCTC and equity research PDFs. | 1. Open `https://finance.vietstock.vn/FPT/tai-chinh.htm`<br>2. Switch between Balance Sheet and Income Statement tabs<br>3. Go to `Báo cáo phân tích` tab and click download on a broker report<br>4. Save Network HAR. |
| **4** | **Ngân hàng Nhà nước VN (`sbv.gov.vn`)** | Oracle WebCenter Portal with stateful dynamic session paths (`/webcenter/portal/...`) that block automated deep pagination. | 1. Go to `https://sbv.gov.vn/webcenter/portal/vi/menu/trangchu/vbqppl`<br>2. Search circulars (*Thông tư*) in monetary policy<br>3. Paginate 2 pages<br>4. Save Network HAR. |
| **5** | **Thư viện Pháp luật (`thuvienphapluat.vn`)** | Aggressive IP throttling and login walls for historical legal documents prior to 2015. | 1. Log in to an account<br>2. Search economic decrees (e.g., *Nghị định chứng khoán*, *Luật Đất đai*)<br>3. Open 2–3 decrees with full text<br>4. Save Network HAR. |
| **6** | **Trading Economics (`tradingeconomics.com/vietnam`)** | Cloudflare Turnstile bot challenges completely block headless HTTP clients. | 1. Open `https://tradingeconomics.com/vietnam/indicators`<br>2. Click on "Interest Rate", "Inflation Rate", "GDP"<br>3. Save Network HAR. |
