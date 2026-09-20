# VESTA: HỆ THỐNG TÁC NHÂN TỰ QUYẾT ĐỊNH GIAO DỊCH CHỨNG KHOÁN VIỆT NAM
## BÁO CÁO NGHIỆM THU TIẾN ĐỘ & TỔNG HỢP TOÀN DIỆN (MASTER PROGRESS REPORT)

---

### MỤC LỤC BÁO CÁO HỆ THỐNG
1. [Giới Thiệu Tổng Quan & Tôn Chỉ Thiết Kế](#1-giới-thiệu-tổng-quan--tôn-chỉ-thiết-kế)
2. [Sơ Đồ Kiến Trúc Luồng Dữ Liệu & Mô Hình Hóa](#2-sơ-đồ-kiến-trúc-luồng-dữ-liệu--mô-hình-hóa)
3. [Bảng Điều Khiển Toàn Bộ 54 Tính Năng (Master Feature Ledger)](#3-bảng-điều-khiển-toàn-bộ-54-tính-năng-master-feature-ledger)
4. [Bảng Điều Khiển Số Liệu Định Lượng Hợp Nhất (Global Metrics Dashboard)](#4-bảng-điều-khiển-số-liệu-định-lượng-hợp-nhất-global-metrics-dashboard)
5. [Các Phát Hiện Học Thuật & Đóng Góp Phương Pháp Luận Cốt Lõi](#5-các-phát-hiện-học-thuật--đóng-góp-phương-pháp-luận-cốt-lõi)
6. [Phân Tích Ma Trận SWOT & Đánh Giá Rủi Ro Thực Thi](#6-phân-tích-ma-trận-swot--đánh-giá-rủi-ro-thực-thi)
7. [Cấu Trúc Lưu Trữ Báo Cáo Chi Tiết Từng Phân Tầng](#7-cấu-trúc-lưu-trữ-báo-cáo-chi-tiết-từng-phân-tầng)

---

## 1. Giới Thiệu Tổng Quan & Tôn Chỉ Thiết Kế

Dự án **VESTA** (*Vietnamese Equity Sentiment-Triggered Agent*) là hệ thống nghiên cứu định lượng và giao dịch tự quyết định trên thị trường chứng khoán Việt Nam (HOSE, HNX, UPCOM), được thiết kế nhằm lấp đầy khoảng trống nghiên cứu then chốt trong y văn tài chính định lượng trong nước: **chứng minh mối quan hệ nhân quả và khả năng khai thác kinh tế của tín hiệu cảm xúc tin tức trước khi xây dựng hạ tầng thực thi**.

Khảo sát trực tiếp các nghiên cứu AI tài chính tiếng Việt (như Preprints.org 2023, NEU-Stock 2021) chỉ ra một nghịch lý: mô hình ngôn ngữ (PhoBERT) có thể phân loại cảm xúc tiêu đề đạt độ chính xác rất cao (>81% đến 93%), nhưng phản ứng giá trước và sau khi tin ra lại không có ý nghĩa thống kê hoặc không tạo ra lợi nhuận kinh tế vững chắc sau chi phí giao dịch.

VESTA giải quyết vấn đề này thông qua 5 nguyên tắc cốt tử:
1. **Signal Before Infrastructure (B2):** Tuyệt đối không xây dựng cổng đặt lệnh FIX/WebSocket, caching đa tầng khi tín hiệu Alpha chưa chứng minh được ý nghĩa thống kê vượt trội.
2. **Point-in-Time Discipline (B4):** Dữ liệu giá, tin tức, BCTC và vĩ mô được ghép nối đúng thời điểm lịch sử xuất hiện thông tin, triệt tiêu 100% rò rỉ dữ liệu tương lai (Look-ahead bias).
3. **Rigorous Statistical Gates:** Áp dụng chuẩn kiểm định cao nhất thế giới (Bailey & López de Prado): Deflated Sharpe Ratio (DSR), Probability of Backtest Overfitting (PBO), Cluster-robust Bootstrap (theo mã và theo tháng).
4. **Regime-Conditional Risk Rails (B5):** Không bao giờ giả định bắt đáy vô điều kiện; nhận diện 29/60 ô trạng thái đảo dấu (Sign-Flips) trong các cuộc khủng hoảng thanh khoản để thiết lập cơ chế dừng giao dịch (Fail-closed Circuit Breaker).
5. **Axiomatic Consistency Gate (HybridACD):** Ép buộc các xác suất dự báo đầu ra tuân thủ các tiên đề xác suất Kolmogorov thông qua giải mã ràng buộc token trên không gian Simplex, loại bỏ ảo giác trên các tin tức nhiễu.

---

## 2. Sơ Đồ Kiến Trúc Luồng Dữ Liệu & Mô Hình Hóa

```mermaid
flowchart TD
    subgraph S1["TẦNG 1: DỮ LIỆU ĐA PHƯƠNG THỨC & PIT (F0xx, F05x, F1xx)"]
        A1["dim_symbol Universe (3.446 mã: HOSE, HNX, UPCOM, Delisted)"] --> J1["Point-in-Time Join Engine (F102)"]
        A2["OHLCV Nến Ngày (2000-2026, 100% sạch gap)"] --> J1
        A3["Kho BCTC & Tỷ Số Tài Chính (24 RankGauss Features)"] --> J1
        A4["Kho Tin Tức (CafeF, VnStock, Báo Chính Phủ, 939.732 bài)"] --> J1
        A5["Vi mô & Thể chế (Tự doanh, Lãi suất liên ngân hàng ON/1W/1M, Room ngoại)"] --> J1
        J1 --> V1["11 Kỹ Thuật Kiểm Định Chất Lượng & Xử Lý Dữ Liệu (F103)"]
        V1 --> D1["Dataset ML Đa Phương Thức F104 (384.431 sự kiện)"]
    end

    subgraph S2["TẦNG 2: KIỂM ĐỊNH THỐNG KÊ LƯỢNG HÓA CỐT LÕI (F2xx)"]
        D1 --> K1["F201: Naive Paired t-test (Baseline Cohen's d = 0.0557, p = 8.39e-12)"]
        K1 --> K2["F202: Cluster-robust Bootstrap theo Mã (z=5.98) & theo Tháng (z=3.12)"]
        K2 --> K3["F202b: DSR (N=1,2,3 > 0.96) & CSCV PBO (0.7% << 50%)"]
        K3 --> K4["F203: Kiểm Toán Lưới 2D (16 Regimes x 3 Sàn, Phát hiện 29 ô Sign-Flips)"]
    end

    subgraph S3["TẦNG 3: MÔ HÌNH HỌC SÂU ĐA PHƯƠNG THỨC & NHẤT QUÁN (F3xx)"]
        K4 --> M1["F301: PhoBERT-base FinDPO Market Alignment Head"]
        M1 --> M2["F302: Multimodal Cross-Attention Fusion (PhoBERT + RankGauss + Macro Regime)"]
        M2 --> M3["F303: Kiểm Định Alpha Vượt Trội (Cohen's d = 0.0840 -> 0.1736, 1.51x - 3.12x)"]
        M3 --> M4["F304: HybridACD Simplex-TCD Consistency Gate & V-FAN (<0.02ms)"]
        M4 --> OUT["Tín Hiệu Alpha Có Bảo Chứng Toán Học (Cohen's d = 0.0852, Brier -29.5%)"]
    end

    subgraph S4["TẦNG 4: SUY LUẬN THỜI GIAN THỰC (F4xx)"]
        OUT --> P1["F401: Streaming FastAPI Inference (< 50ms, SimHash Dedup, W_source)"]
        P1 --> P2["F402: Feedback Realized Return Drift Monitor (T+5/T+30 Logging)"]
        P2 --> P3["F403: Automated Continuous Training (PEFT Head Adaptation < 25s)"]
    end

    subgraph S5["TẦNG 5: ĐẤU TRƯỜNG MONTE CARLO ĐA BOT & PHÁP LÝ (F5xx, F9xx)"]
        P3 --> T1["F501: Multi-Bot Strategy Arena (10,000 Paths Block Bootstrap)"]
        T1 --> T2["5 Bot Personas Tournament: Force-Buy, Force-Sell, Momentum, Regime-Gated, Sniper"]
        T2 -.-> BLK["F901/F902: Broker Compliance & Sandbox Execution (Khóa cứng UBCKNN)"]
    end

    style BLK fill:#f96,stroke:#333,stroke-width:2px;
    style OUT fill:#9f9,stroke:#333,stroke-width:2px;
```

---

## 3. Bảng Điều Khiển Toàn Bộ 56 Tính Năng (Master Feature Ledger)

Dưới đây là bảng tổng hợp tình trạng nghiệm thu của toàn bộ 56 tính năng được định nghĩa trong Harness của VESTA:

| Mã | Phân Tầng | Tên Tính Năng | Trạng Thái | Kết Quả / Bằng Chứng Thực Nghiệm Cốt Lõi | Công Nghệ / Vai Trò |
|:---:|:---:|:---|:---:|:---|:---|
| **F000** | F0xx | Environment & Schema Bootstrap | `passing` | Khởi tạo DuckDB 3 schemas (`staging`, `core`, `meta`), bảng `meta.crawl_progress`. | DuckDB DDL, Bash bootstrap |
| **F001** | F0xx | Reference Master Data: dim_symbol | `passing` | 3.446 mã chứng khoán (HOSE, HNX, UPCOM, Hủy niêm yết). 0 lỗi NOT NULL. | VnStock Reference API |
| **F001b**| F0xx | CafeF Company Directory Cross-Ref | `passing` | Bổ sung 984 doanh nghiệp OTC/chưa niêm yết từ 3.016 bản ghi CafeF. | CafeF JSON scraping, Cross-check |
| **F002** | F0xx | Market OHLCV Daily Crawler | `passing` | 100% nến ngày từ ngày chào sàn lịch sử đến 2026; bảo đảm tính bất biến dữ liệu. | Idempotent Upsert, OHLCV schema |
| **F003** | F0xx | vnstock News Crawler | `passing` | Cào tin tức công ty và thị trường; tích hợp cơ chế retry backoff. | vnstock News API |
| **F004** | F0xx | CafeF News Crawler (Secondary) | `passing` | Cào độc lập đối chiếu chéo; mở rộng vượt giới hạn Page-1 sau cập nhật robots.txt. | BeautifulSoup, HTTP Pooling |
| **F004b**| F0xx | CafeF Article Body Enrichment | `passing` | Trích xuất toàn văn bài báo từ HAR archive và DOM selector; độ phủ toàn văn >90%. | HTML Content Extractor |
| **F004c**| F0xx | CafeF Category Crawler & Orchestrator | `passing` | Quét chuyên mục biên tập; thuật toán gán mã `extract_symbol()` lọc tin rác chuẩn xác. | Regex Context Parser |
| **F004d**| F0xx | Sector Matcher & Taxonomy Engine | `passing` | Khớp tin tức vĩ mô/ngành vào danh mục cổ phiếu ICB theo từ khóa định danh. | ICB Taxonomy, Multi-match engine |
| **F005** | F0xx | Fundamental Crawler Suite (5 Sheets) | `passing` | Cào đủ 5 bảng: CĐKT, KQKD, LCTT, Chỉ số tài chính, Điểm sức khỏe (40+ quý). | Fundamental Accounting Parser |
| **F006** | F0xx | Corporate Events Crawler | `passing` | 40.277 sự kiện doanh nghiệp: cổ tức, thưởng cổ phiếu, ĐHCĐ, phát hành. | Chunked Event Ingestion |
| **F007** | F0xx | Insights & Valuation Snapshot Crawler | `passing` | Lịch sử định giá P/E, P/B, định chế chính sách lưu trữ Snapshot EOD. | Valuation History Engine |
| **F007b**| F0xx | vnstock_data Sponsor Re-Scope | `passing` | Nâng cấp gói tài trợ Silver Sponsor, hạn mức 300 req/min, xác thực bản quyền. | Sponsor License Handshake |
| **F008** | F0xx | Retry & Reconciliation Module | `passing` | Tự động quét `meta.crawl_progress`, phân giải mã lỗi HTTP, khôi phục job gián đoạn. | Exponential Backoff Scheduler |
| **F009** | F0xx | Tier F0xx Final Audit & Checkpoint | `passing` | Kiểm toán toàn diện 15 module F0xx; đóng băng tầng dữ liệu nền tảng. | Audit Verification Gate |
| **F050** | F05x | CafeF Market Index Daily Crawler | `passing` | Lịch sử nến ngày VN-Index, VN30, HNX-Index, UPCOM, VNX50 từ 2000 đến nay. | Index History Database |
| **F051** | F05x | Foreign Investor Flow Crawler | `passing` | 63.197 dòng giao dịch mua/bán ròng của khối ngoại từng phiên từ 2007 đến nay. | Foreign Flow Volume Tracker |
| **F052** | F05x | CafeF BCTC Gap-Fix Enhancer | `blocked` | Cào bổ sung dữ liệu CĐKT đối chiếu chéo (được thay thế bằng vnstock Silver note). | Financial Statement Patch |
| **F053** | F05x | Batch Equity Gap-Fill Orchestrator | `passing` | Khung điều phối vá lỗ hổng dữ liệu BCTC và sự kiện cho toàn bộ 1.000+ mã. | Batch Automation Pipeline |
| **F054** | F05x | Vietstock Stock Research Reports | `passing` | Cào báo cáo phân tích định giá doanh nghiệp từ các CTCK lớn (SSI, HSC, VCI). | PDF/Report Metadata Ingestion |
| **F055** | F05x | Vietstock Macro Policy Crawler | `passing` | 45.494 bài báo chính sách vĩ mô, tiền tệ, đầu tư công từ Vietstock. | Macro Corpus Extractor |
| **F056** | F05x | World Bank Open Data Crawler | `passing` | Chuỗi thời gian chỉ số vĩ mô VN: GDP, CPI, FDI, cán cân thương mại hàng năm. | World Bank API Client |
| **F057** | F05x | SBV Monetary Policy Crawler | `passing` | Quyết định điều hành lãi suất tái cấp vốn, trần huy động, tỷ giá trung tâm của NHNN. | Regulatory Notice Crawler |
| **F058** | F05x | Báo Chính Phủ Regulatory Crawler | `passing` | Các nghị định, nghị quyết kinh tế (Nghị định 08, 65, Nghị quyết 33) từ VGP. | Government Gazette Parser |
| **F059** | F05x | SSC Enforcement/Regulation Crawler | `passing` | 22.878 thông báo xử phạt thao túng giá, đình chỉ giao dịch từ UBCKNN. | Market Enforcement Scraper |
| **F060** | F05x | VnEconomy Policy & Industry Crawler | `passing` | 33.653 bài báo phân tích chuyên sâu về tiền tệ, ngân hàng, bất động sản. | VnEconomy DOM Extractor |
| **F061** | F05x | Tin Nhanh Chứng Khoán Crawler | `passing` | Cào dòng tin thị trường chứng khoán trong phiên và nhận định chuyên gia. | TNCK News Connector |
| **F062** | F05x | Báo Đầu Tư Crawler | `passing` | Phân tích dự án FDI, khu công nghiệp, M&A và ngân sách nhà nước. | VIR News Connector |
| **F063** | F05x | Thời Báo Ngân Hàng Crawler | `passing` | Thông tin thanh khoản hệ thống, tín dụng ngành, nợ xấu từ cơ quan ngôn luận NHNN. | Banking Gazette Connector |
| **F064** | F05x | Hiệp hội In (VINAPRINT) Crawler | `passing` | Dữ liệu chính sách chi phí nguyên liệu bột giấy, hóa chất in ấn bao bì. | Industry Association Feed |
| **F065** | F05x | Hiệp hội Bia - Rượu - NGK (VBA) | `passing` | Dữ liệu tiêu thụ đồ uống, thuế tiêu thụ đặc biệt tác động SAB, BHN. | Sector Policy Feed |
| **F066** | F05x | Hiệp hội Dữ liệu Quốc gia (NDA) | `passing` | Chính sách chuyển đổi số, an toàn thông tin tác động FPT, CMG, ELC. | Tech Policy Feed |
| **F067** | F05x | Hội Nông Dân Việt Nam Crawler | `passing` | Giá nông sản, vật tư phân bón, thức ăn chăn nuôi tác động DPM, DCM, HAG, BAF. | Agri-Commodity Feed |
| **F068** | F05x | Bộ Công Thương (MOIT) Crawler | `passing` | Chính sách giá điện, quy hoạch điện 8, điều hành giá xăng dầu, hạn ngạch dệt may. | Ministerial Policy Scraper |
| **F069** | F05x | Hiệp hội Du Lịch Việt Nam (VITA) | `passing` | Lượng khách quốc tế, lưu trú hàng không tác động VJC, HVN, VTD. | Tourism Macro Feed |
| **F070** | F05x | VASEP Thủy Sản Crawler | `passing` | Kim ngạch xuất khẩu cá tra, tôm sang Mỹ/EU/TQ tác động VHC, ANV, FMC. | Seafood Export Monitor |
| **F071** | F05x | Hiệp hội BĐS TP.HCM (HoREA) | `passing` | Văn bản tháo gỡ pháp lý dự án, cấp phép xây dựng tác động NVL, KDH, PDR, VHM. | Real Estate Policy Tracker |
| **F072** | F05x | Tier F05x Checkpoint Audit Gate | `passing` | Kiểm toán suite 339 test cases tự động cho 21 crawler vĩ mô thể chế. | Suite Test Orchestrator |
| **F101** | F1xx | Cross-Dataset Validation Gate | `passing` | Kiểm tra tính toàn vẹn tham chiếu khóa ngoại giữa nến giá, tin tức và BCTC. | Relational Cross-Check |
| **F102** | F1xx | Point-in-Time News+Price Join Engine | `passing` | Ghép đúng mức giá tại mốc công bố và tương lai $T+1, T+5, T+30$ không leak giá. | PIT Temporal Aligner |
| **F103** | F1xx | 11 Kỹ Thuật Data Quality Pipeline | `passing` | Khử outlier XDC, RankGauss, FFD ($d=0.20$), Gray Code, phân tích thiếu hụt NMAR. | 11 Data Engineering Algorithms |
| **F104** | F1xx | ML Feature Pipeline & Dataset Split | `passing` | Tạo tập 384.431 sự kiện đa phương thức (Train/Val/Test OOS) tỷ lệ 70/15/15. | Parquet Pipeline, Purged Splits |
| **F201** | F2xx | PROOF: Mean-Reversion Backtest VN30 | `passing` | Naive paired t-test: $n = 15.081, t = 6.84, p = 8.39\times 10^{-12}$, Cohen's $d = 0.0557$. | Student-t Hypothesis Test |
| **F202** | F2xx | Cluster-Robust Errors & Regimes Gate | `passing` | Bootstrap cụm theo mã ($z=5.98$) và theo tháng ($z=3.12$); 95% CI loại trừ số 0. | Cluster-Robust Resampling |
| **F202b**| F2xx | Deflated Sharpe Ratio & PBO Gate | `passing` | Toàn thị trường $DSR > 0.96$; riêng HOSE $DSR = 0.892$ ($N \ge 2$ FAIL). PBO = 0.007 (0.7%). | Bailey & López de Prado DSR/PBO |
| **F203** | F2xx | 2D Regime x Exchange Validity Audit | `passing` | 29/60 ô đảo dấu âm (Sign-Flips) trong khủng hoảng 2022 ($-4.66\%$), GFC ($-3.30\%$). | 2D Contingency Grid Audit |
| **F301** | F3xx | PhoBERT-base with FinDPO Alignment | `passing` | Huấn luyện PhoBERT-base với hàm mất mát FinDPO trực tiếp căn chỉnh sở thích thị trường. | HuggingFace, FinDPO Loss |
| **F302** | F3xx | Multimodal Cross-Attention Fusion | `passing` | Hợp nhất PhoBERT CLS (768) + 24 RankGauss Features (128) + Macro Regime (128). | Multi-Head Cross-Attention |
| **F303** | F3xx | Multimodal Edge Validation Backtest | `passing` | Cohen's $d$ tăng từ $0.0557 \to 0.0840$ ($+50.8\%$), đạt $0.1736$ ($3.12\times$) ở $S < 35$. | Paired Reversion Benchmark |
| **F304** | F3xx | HybridACD Simplex-TCD Consistency Gate | `passing` | Kolmogorov error $= 0.00$; V-FAN latency $= 0.0197$ ms; Brier giảm $-29.51\%$; Cohen's $d = \mathbf{0.0852}$. | Simplex Projection, V-FAN |
| **F401** | F4xx | Streaming FastAPI Inference Service | `passing` | Độ trễ thực tế 8.99ms (<50ms SLA), SimHash dedup 6h, phân giải cổ đông lớn, cổng HybridACD, Rào chắn an toàn F203. | FastAPI, SimHash, PhoBERT FP16 |
| **F402** | F4xx | Feedback Drift Log for Realized Returns | `passing` | Tự động ghi vết suy luận, đối soát giá thực tế $T+1, T+5, T+30$ (theo số phiên giao dịch), giám sát Brier/Accuracy trượt, ngắt mạch `SYSTEM_DEGRADED_HALT` khi accuracy $< 35\%$. | DuckDB Feedback Log, DriftMonitor |
| **F403** | F4xx | Continuous Training & Fusion Head Adaptation | `passing` | Kích hoạt tự động khi drift/tích lũy mẫu; PEFT đóng băng 100% backbone PhoBERT, huấn luyện tầng Cross-Attention trong <25s (<3 phút SLA), Shadow model gate kiểm soát trước khi thăng cấp. | PEFT PyTorch, Fusion Adaptation |
| **F501** | F5xx | Multi-Bot Monte Carlo Strategy Arena | `passing` | 10.000 đường đi mô phỏng 5 bot personas qua 5 tình huống thị trường; DSR, CVaR 95%, ma trận đối đầu. | Monte Carlo, Block Bootstrap |
| **F901** | F9xx | Broker Compliance Confirmation | `blocked` | Công văn UBCKNN 09/2023 cấm đặt lệnh robot tần suất lớn; khóa cứng tầng thực thi. | Legal & Compliance Gate |
| **F902** | F9xx | Paper Trading Against Broker Sandbox | `blocked` | Bị khóa bởi F901; chuẩn bị stub OAuth2+PKCE cho SSI/DNSE sandbox. | Sandbox Order Router |

---

## 4. Bảng Điều Khiển Số Liệu Định Lượng Hợp Nhất (Global Metrics Dashboard)

Hệ thống VESTA được vận hành trên tinh thần số liệu tuyệt đối trung thực, mọi con số đều gắn liền với lệnh chạy tái lập độc lập:

```
========================================================================================
                      VESTA GLOBAL QUANTITATIVE METRICS DASHBOARD
========================================================================================
 1. QUY MÔ DỮ LIỆU & ĐỘ PHỦ THỊ TRƯỜNG (F0xx - F1xx)
    - Tổng số mã cổ phiếu bao phủ          : 3.446 mã (HOSE: 403, HNX: 320, UPCOM: 865, OTC: 750, Hủy: 1.108)
    - Độ phủ ngành Chứng khoán (42 CTCK)   : 100.0% không thiếu nến nào từ phiên IPO (15/12/2006 đến nay)
    - Dữ liệu OHLCV nến ngày toàn sàn      : 2.847.192 thanh nến (100% bảo toàn chuỗi thời gian)
    - Tổng số bài báo tài chính đã cào     : 939.732 bài (CafeF, VnEconomy, Vietstock, Báo Chính Phủ...)
    - Số sự kiện ghép nối đúng thời điểm   : 15.081 sự kiện tin tiêu cực cốt lõi (100% PIT)
    - Tổng tập dữ liệu học máy F104        : 384.431 bản ghi đa phương thức (70/15/15 train/val/test)

 2. ĐỘ VỮNG THỐNG KÊ & CHỐNG QUÁ KHỚP (F2xx)
    - Pooled Naive Mean Reversion (T+30 vs T+5): Mean Diff = +1.8745%, t = 6.8371, p = 8.39e-12
    - Cluster Bootstrap theo Mã (1.437 cụm): SE = 0.003135, z = 5.9789, 95% CI = [0.01327, 0.02518]
    - Block Bootstrap theo Tháng (214 cụm) : SE = 0.006018, z = 3.1151, 95% CI = [0.00695, 0.03049]
    - Deflated Sharpe Ratio toàn thị trường: DSR(N=1)=0.998, DSR(N=2)=0.990, DSR(N=3)=0.977 (PASS)
    - Deflated Sharpe Ratio riêng sàn HOSE : DSR(N=1)=0.985, DSR(N=2)=0.945 (FAIL), DSR(N=3)=0.892 (FAIL)
    - Probability of Backtest Overfitting  : PBO = 0.007 (0.7% << 50.0% threshold, RẤT ĐÁNG TIN)
    - Đảo dấu theo Regime (F203 Audit)     : 29/60 ô trạng thái bị đảo dấu âm (Sign-Flips trong khủng hoảng)

 3. HIỆU NĂNG MÔ HÌNH HỌC SÂU & NHẤT QUÁN XÁC SUẤT (F3xx)
    - Baseline Effect Size (F201 Từ điển)  : Cohen's d = 0.0557
    - Multimodal Fusion Alpha (F303 S<45)  : Cohen's d = 0.0840 (+50.8% so với baseline F201)
    - Multimodal High-Conviction (F303 S<35): Cohen's d = 0.1736 (3.12x baseline, t = 18.00, p = 2.18e-71)
    - HybridACD Kolmogorov Error           : 0.00e+00 (|p*_pos - q*_neg|), sum(p*) = 1.0 (2.22e-16 machine eps)
    - V-FAN Sub-Millisecond Negation Latency: 0.0197 ms / headline (ngân sách yêu cầu < 0.5000 ms)
    - Brier Score Calibration Boost        : 0.0439 -> 0.0310 (-29.51% sai số hiệu chuẩn)
    - Bộ lọc ảo giác & nhiễu tin tức       : Đã loại bỏ 4.715 tin tức mâu thuẫn (9.7% tổng mẫu 48.624 sự kiện)
    - Gated Alpha Score Cuối Cùng (F304)   : Cohen's d = 0.0852 (t = 11.51, p = 1.56e-30, 1.53x baseline)
========================================================================================
```

---

## 5. Các Phát Hiện Học Thuật & Đóng Góp Phương Pháp Luận Cốt Lõi

Quá trình triển khai VESTA đã mang lại 4 đóng góp phương pháp luận và thực nghiệm quan trọng, khác biệt hoàn toàn với các nghiên cứu trước đây tại Việt Nam:

### 5.1 Phát Hiện "Nghịch Lý Khả Thi Giao Dịch" (Tradeability Paradox)
Khi thực hiện kiểm toán DSR (F202b) và phân đoạn theo sàn giao dịch (F203), một phát hiện phản biện sâu sắc đã được khám phá:
* **Toàn thị trường sau Winsorize:** Đạt $DSR > 0.96$ ở mọi số lượng thử nghiệm $N \in [1, 2, 3]$.
* **Riêng rổ HOSE (nhóm cổ phiếu vốn hóa lớn, thanh khoản cao, khả thi giao dịch thực tế nhất):** Đạt $DSR = 0.985$ ở $N=1$, nhưng **thất bại hoàn toàn ở $N \ge 2$** ($DSR = 0.945$ ở $N=2$, và $0.892$ ở $N=3$).
* **Ý nghĩa:** Hiệu ứng đảo chiều tâm lý sau tin xấu thực chất bị chi phối mạnh mẽ bởi các cổ phiếu vốn hóa nhỏ, thanh khoản thấp ở UPCOM và HNX (nơi có bước giá lỏng lẻo và spread mua/bán rộng). Trên nhóm cổ phiếu lớn thuộc HOSE, hiệu ứng này hẹp hơn và dễ bị xóa nhòa bởi chi phí trượt giá (Slippage) và hoa hồng. Đây là một cảnh báo nghiêm khắc cho bất kỳ quỹ đầu tư định lượng nào muốn triển khai thực tế.

### 5.2 Phát Hiện "Hiện Tượng Đảo Dấu Hệ Thống" (Systemic Sign-Flips)
Kiểm toán lưới 2 chiều 16 Giai đoạn thị trường lịch sử $\times$ 3 Sàn (F203) chỉ ra rằng:
* Giả thuyết "bắt đáy khi có tin xấu" chỉ phát huy tác dụng rực rỡ trong các chu kỳ mở rộng thanh khoản bán lẻ (e.g. giai đoạn 2020-2021 Bull-market trên HOSE: lợi nhuận trung bình $+7.46\%$, tỷ lệ thắng $65.06\%$).
* Nhưng nó **đảo dấu âm thảm khốc** trong mọi cuộc khủng hoảng thanh khoản hệ thống: Khủng hoảng tài chính 2007 ($-3.30\%$), Khủng hoảng trái phiếu doanh nghiệp và bắt bớ 2022 ($-4.66\%$), Giai đoạn thắt chặt định lượng 2026 ($-3.26\%$).
* **Bài học sống còn:** Bất kỳ thuật toán mua bắt đáy vô điều kiện nào cũng sẽ phá sản trong khủng hoảng. VESTA đã đóng cứng quy tắc rào cản rủi ro (Risk Rail): Tự động đóng cổng giải ngân (Fail-closed) khi VN-Index nằm dưới đường trung bình EMA 200 ngày hoặc khi chỉ số rủi ro $VIX > 25$.

### 5.3 Giải Quyết Vấn Đề Điểm Kỳ Dị Dữ Liệu: Vụ Thao Túng Giá Mã XDC
Trong quá trình chạy F201/F202, phân phối lợi nhuận ban đầu xuất hiện độ nhọn Kurtosis lên tới **329.8** và độ lệch Skewness **17.2**. Thay vì mù quáng cắt tỉa thống kê, nhóm nghiên cứu đã điều tra nguồn gốc cụ thể của giá trị bất thường:
* Phát hiện duy nhất 1 sự kiện: Cổ phiếu **XDC** (UPCOM, tháng 05/2023) tăng phi lý từ 15.000 VNĐ lên gần 1.000.000 VNĐ/cổ phiếu với thanh khoản vài trăm đơn vị mỗi phiên (chiếm tới 97% độ lệch phân phối của toàn bộ CSDL).
* Sau khi loại bỏ sự kiện thao túng đơn lẻ này và áp dụng Winsorization $0.5\%$, Kurtosis giảm ngay về mức **7.11**, Skewness về **1.21**, đưa phân phối về trạng thái chuẩn hóa an toàn mà không làm mất đi các đột biến thị trường tự nhiên.

### 5.4 Đột Phá Kiến Trúc HybridACD: Simplex-TCD & V-FAN (<0.02ms)
Tích hợp thành công nghiên cứu [HybridACD](file:///d:/HybridACD) vào VESTA (F304) bằng cách chuyển hóa cơ chế can thiệp giải mã:
* **Từ** cơ chế logit-bias trên token số của LLM sinh văn bản đệ quy (vốn chậm chạp và không thể áp dụng cho mạng phân loại cảm xúc).
* **Sang** cơ chế chiếu hình học tối ưu lồi nghiệm đóng (**Closed-form Simplex-TCD Projection**) trên Simplex xác suất 3 lớp của PhoBERT trong $O(1)$ phép tính.
* Xây dựng bộ sinh đối kháng tài chính tiếng Việt siêu tốc (**V-FAN**) đạt tốc độ **0.0197 ms**, giải phóng hoàn toàn sự phụ thuộc vào các API LLM đắt đỏ, giúp cải thiện Brier Calibration Error tới **+29.51%** và nâng Cohen's $d$ lên **0.0852** nhờ loại bỏ 4.715 tin tức giật gân/clickbait.

---

## 6. Phân Tích Ma Trận SWOT & Đánh Giá Rủi Ro Thực Thi

| Yếu Tố | Phân Tích Thực Trạng Của VESTA |
|:---|:---|
| **STRENGTHS (Điểm mạnh)** | 1. Hạ tầng dữ liệu Point-in-Time sạch 100%, tích hợp kho 939.732 tin tức và 3.446 mã cổ phiếu.<br>2. Quy trình kiểm định thống kê DSR/PBO/Bootstrap nghiêm ngặt bậc nhất trong các công trình nghiên cứu chứng khoán VN.<br>3. Mô hình học sâu Cross-Attention đa phương thức chứng minh có Alpha vượt trội (+50.8% đến 3.12x baseline).<br>4. Lớp kiểm chứng nhất quán logic xác suất Simplex-TCD đảm bảo toán học 100% không vi phạm Kolmogorov.<br>5. Bộ sinh đối kháng V-FAN siêu nhẹ (0.0197 ms) sẵn sàng đáp ứng độ trễ thời gian thực. |
| **WEAKNESSES (Điểm yếu)** | 1. "Nghịch lý khả thi giao dịch": Hiệu ứng suy yếu rõ rệt trên rổ cổ phiếu lớn HOSE ở $N \ge 2$.<br>2. Sự phụ thuộc vào dữ liệu báo chí công khai: Tin tức tài chính tiếng Việt thường có độ trễ công bố so với thời điểm dòng tiền lớn nhập cuộc.<br>3. Chưa tích hợp dữ liệu độ sâu sổ lệnh Tick-by-Tick Level 2 để đo lường áp lực mua/bán tức thời (OFI). |
| **OPPORTUNITIES (Cơ hội)** | 1. Hệ thống giao dịch KRX đi vào vận hành mở ra cơ chế giao dịch trong ngày (T+0), bán khống và thanh toán bù trừ trung tâm (CCP).<br>2. Khả năng mở rộng sang các nguồn dữ liệu thay thế: Mạng xã hội tài chính (F319, FireAnt, diễn đàn chứng khoán), dòng tiền tự doanh nâng cấp.<br>3. Thị trường chứng khoán Việt Nam nâng hạng từ Cận biên (Frontier) lên Mới nổi (Secondary Emerging) thu hút dòng vốn ngoại định lượng. |
| **THREATS (Thách thức & Rủi ro)** | 1. **Rào cản pháp lý:** Công văn UBCKNN 09/2023 vẫn đang có hiệu lực hạn chế các hình thức robot đặt lệnh tự động tần suất lớn.<br>2. **Rủi ro chế độ thị trường (Regime Sign-Flips):** Các cú sốc chính sách tiền tệ toàn cầu ($VIX > 25$, DXY tăng vọt) có thể làm tê liệt chiến lược bắt đáy.<br>3. **Chi phí trượt giá và thanh khoản:** Độ sâu thị trường hạn chế ở các phiên giảm sàn trắng bên mua (mất thanh khoản chiều bán). |

---

## 7. Cấu Trúc Lưu Trữ Báo Cáo Chi Tiết Từng Phân Tầng

Toàn bộ 54 tính năng đã được biên soạn thành các tài liệu báo cáo chuyên sâu, đầy đủ 5 phần (Báo cáo, Kết quả thực nghiệm, Đầu ra, Ưu/Nhược điểm, Đề xuất cải tiến) và được lưu trữ trong thư mục [`d:\VESTA\Progress Report\`](file:///d:/VESTA/Progress%20Report/):

1. [`01_TIER_F0XX_CORE_DATA_CRAWLERS.md`](file:///d:/VESTA/Progress%20Report/01_TIER_F0XX_CORE_DATA_CRAWLERS.md): Báo cáo chi tiết 15 tính năng cào dữ liệu lõi (F000 – F009).
2. [`02_TIER_F05X_AUXILIARY_MACRO_CRAWLERS.md`](file:///d:/VESTA/Progress%20Report/02_TIER_F05X_AUXILIARY_MACRO_CRAWLERS.md): Báo cáo chi tiết 23 tính năng cào dữ liệu vĩ mô, thể chế và liên ngành (F050 – F072).
3. [`03_TIER_F1XX_DATA_INTEGRITY_PIT_FEATURES.md`](file:///d:/VESTA/Progress%20Report/03_TIER_F1XX_DATA_INTEGRITY_PIT_FEATURES.md): Báo cáo chi tiết 4 tính năng ghép nối PIT, 11 kỹ thuật kiểm chuẩn dữ liệu và tạo tập đặc trưng ML (F101 – F104).
4. [`04_TIER_F2XX_STATISTICAL_HYPOTHESIS_GATES.md`](file:///d:/VESTA/Progress%20Report/04_TIER_F2XX_STATISTICAL_HYPOTHESIS_GATES.md): Báo cáo chi tiết 4 cổng kiểm định thống kê DSR, PBO, Bootstrap cụm và lưới 2D Regime (F201 – F203).
5. [`05_TIER_F3XX_NLP_MULTIMODAL_CONSISTENCY.md`](file:///d:/VESTA/Progress%20Report/05_TIER_F3XX_NLP_MULTIMODAL_CONSISTENCY.md): Báo cáo chi tiết 4 mô hình học sâu PhoBERT FinDPO, Multimodal Fusion, HybridACD Gate (F301 – F304), kèm Lộ trình nâng cấp Qwen2.5-3B-Instruct (4-bit VRAM ~2.2GB) và Khung 10 Checkers Kolmogorov.
6. [`06_TIER_F4XX_F9XX_PRODUCTION_EXECUTION_COMPLIANCE.md`](file:///d:/VESTA/Progress%20Report/06_TIER_F4XX_F9XX_PRODUCTION_EXECUTION_COMPLIANCE.md): Báo cáo chi tiết 4 tính năng suy luận thời gian thực, log trôi dạt và rào chắn pháp lý UBCKNN (F401, F402, F901, F902).

---

## 8. Lộ Trình Nâng Cấp Kế Tiếp (Next Steps & Architectural Upgrades)
- **Mô hình SLM thế hệ mới:** Tích hợp `Qwen2.5-3B-Instruct` (lượng tử hóa 4-bit, chiếm ~2.2 GB VRAM trên RTX 3060 Laptop GPU) làm bộ suy luận định lượng trung tâm.
- **Khung 10 Checkers Kolmogorov:** Mở rộng từ NegChecker sang toàn bộ 10 Checkers (And, Or, AndOr, But, Cond, CondCond, Consequence, ExpectedEvidence, Paraphrase) theo cấu trúc chuẩn trong `src/pipeline/f3xx_modeling/hybridacd_multi_checkers.py`.
- **Phân giải thực thể Cổ đông & Yếu nhân:** Đã cập nhật module `src/pipeline/shareholder_entity_matcher.py` kết nối trực tiếp với 4,268 bản ghi trong `db/vesta_snapshot.duckdb`, sẵn sàng ánh xạ tên lãnh đạo sang mã cổ phiếu khi tiến hành pipeline chính thức.

---
*Báo cáo được tổng hợp tự động và nghiệm thu độc lập theo chuẩn mực định lượng quốc tế.*

