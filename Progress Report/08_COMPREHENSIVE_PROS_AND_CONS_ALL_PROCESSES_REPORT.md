# BÁO CÁO TỔNG HỢP TOÀN DIỆN: ƯU ĐIỂM & NHƯỢC ĐIỂM CỦA TOÀN BỘ QUY TRÌNH HỆ THỐNG VESTA
## (COMPREHENSIVE PROS AND CONS AUDIT REPORT FOR ALL VESTA PROCESSES)

---

**Dự án:** VESTA (*Vietnamese Equity Sentiment-Triggered Agent*)  
**Mục tiêu:** Kiểm toán, bóc tách và tổng hợp toàn bộ các ưu điểm (Pros), nhược điểm (Cons), điểm nghẽn kỹ thuật (Bottlenecks) và cạm bẫy dữ liệu (Pitfalls) của tất cả các quy trình từ thu thập dữ liệu, tiền xử lý, kiểm định thống kê, mô hình hóa AI/NLP, suy luận thời gian thực, đấu trường Monte Carlo cho đến hành lang pháp lý - thực thi.  
**Chuẩn mực kiểm định:** Marcos López de Prado (*Advances in Financial Machine Learning*), David Bailey (*The Deflated Sharpe Ratio*), Politis & Romano (*Stationary Block Bootstrap*), Kolmogorov Probability Simplex (HybridACD).  
**Ngày phát hành:** 25/09/2026  
**Vị trí lưu trữ:** `d:\VESTA\Progress Report\08_COMPREHENSIVE_PROS_AND_CONS_ALL_PROCESSES_REPORT.md`

---

### MỤC LỤC CHI TIẾT

1. [Lời Mở Đầu & Tôn Chỉ Kiểm Toán Hệ Thống](#1-lời-mở-đầu--tôn-chỉ-kiểm-toán-hệ-thống)
2. [Ma Trận Đánh Giá Tổng Hợp Ưu/Nhược Điểm Toàn Hệ Thống (Master Pros & Cons Matrix)](#2-ma-trận-đánh-giá-tổng-hợp-ưunhược-điểm-toàn-hệ-thống-master-pros--cons-matrix)
3. [Phân Tầng 1: Quy Trình Thu Thập Dữ Liệu Lõi & Hạ Tầng CSDL (Tier F0xx)](#3-phân-tầng-1-quy-trình-thu-thập-dữ-liệu-lõi--hạ-tầng-csdl-tier-f0xx)
   - [3.1. F000: Môi Trường & Kiến Trúc CSDL DuckDB 3-Schema](#31-f000-môi-trường--kiến-trúc-csdl-duckdb-3-schema)
   - [3.2. F001 & F001b: Quản Lý Master Data Danh Bạ Cổ Phiếu & Đối Soát CafeF](#32-f001--f001b-quản-lý-master-data-danh-bạ-cổ-phiếu--đối-soát-cafef)
   - [3.3. F002: Thu Thập & Xác Thực Nến Ngày OHLCV Toàn Thị Trường](#33-f002-thu-thập--xác-thực-nến-ngày-ohlcv-toàn-thị-trường)
   - [3.4. F003: Thu Thập Tin Tức vnstock API](#34-f003-thu-thập-tin-tức-vnstock-api)
   - [3.5. F004, F004b & F004c: Bóc Tách Toàn Văn Báo Chí & Điều Phối CafeF](#35-f004-f004b--f004c-bóc-tách-toàn-văn-báo-chí--điều-phối-cafef)
   - [3.6. F004d: Động Cơ Gắn Thẻ Ngành & Phân Loại Taxonomy ICB](#36-f004d-động-cơ-gắn-thẻ-ngành--phân-loại-taxonomy-icb)
   - [3.7. F005: Bộ Thu Thập Báo Cáo Tài Chính 5 Bảng Kế Toán VAS](#37-f005-bộ-thu-thập-báo-cáo-tài-chính-5-bảng-kế-toán-vas)
   - [3.8. F006: Thu Thập Sự Kiện Doanh Nghiệp & Lịch Quyền](#38-f006-thu-thập-sự-kiện-doanh-nghiệp--lịch-quyền)
   - [3.9. F007 & F007b: Snapshot Bảng Giá Thời Gian Thực & Thăm Dò Sponsor Tier](#39-f007--f007b-snapshot-bảng-giá-thời-gian-thực--thăm-dò-sponsor-tier)
   - [3.10. F008 & F009: Cơ Chế Bù Lỗi Tự Động & Chốt Chặn Kiểm Toán F0xx](#310-f008--f009-cơ-chế-bù-lỗi-tự-động--chốt-chặn-kiểm-toán-f0xx)
4. [Phân Tầng 2: Quy Trình Thu Thập Dữ Liệu Vĩ Mô, Bổ Trợ & Thể Chế (Tier F05x)](#4-phân-tầng-2-quy-trình-thu-thập-dữ-liệu-vĩ-mô-bổ-trợ--thể-chế-tier-f05x)
   - [4.1. F050: Thu Thập Chuỗi Chỉ Số Thị Trường Lịch Sử](#41-f050-thu-thập-chuỗi-chỉ-số-thị-trường-lịch-sử)
   - [4.2. F051: Thu Thập Dòng Tiền Khối Ngoại & Room Sở Hữu](#42-f051-thu-thập-dòng-tiền-khối-ngoại--room-sở-hữu)
   - [4.3. F052 & F053: Vá Lỗ Hổng BCTC & Điều Phối Lô Thanh Khoản](#43-f052--f053-vá-lỗ-hổng-bctc--điều-phối-lô-thanh-khoản)
   - [4.4. F054: Bóc Tách Báo Cáo Phân Tích Doanh Nghiệp CTCK](#44-f054-bóc-tách-báo-cáo-phân-tích-doanh-nghiệp-ctck)
   - [4.5. F055 & F056: Tin Tức Vĩ Mô Vietstock & Dữ Liệu World Bank Open Data](#45-f055--f056-tin-tức-vĩ-mô-vietstock--dữ-liệu-world-bank-open-data)
   - [4.6. F057, F058 & F059: Cơ Quan Quản Lý & Pháp Quy (NHNN, Báo Chính Phủ, UBCKNN)](#46-f057-f058--f059-cơ-quan-quản-lý--pháp-quy-nhnn-báo-chính-phủ-ubcknn)
   - [4.7. F060 - F063: Báo Chí Tài Chính Chuyên Sâu (VnEconomy, TNCK, Đầu Tư, Ngân Hàng)](#47-f060---f063-báo-chí-tài-chính-chuyên-sâu-vneconomy-tnck-đầu-tư-ngân-hàng)
   - [4.8. F064 - F071: 8 Bộ Thu Thập Dữ Liệu Hiệp Hội Ngành & Chuỗi Giá Trị](#48-f064---f071-8-bộ-thu-thập-dữ-liệu-hiệp-hội-ngành--chuỗi-giá-trị)
   - [4.9. F072: Hợp Nhất 7 Staging Database & Kiểm Toán Khóa Ngoại Vĩ Mô](#49-f072-hợp-nhất-7-staging-database--kiểm-toán-khóa-ngoại-vĩ-mô)
5. [Phân Tầng 3: Quy Trình Bảo Đảm Toàn Vẹn, Ghép Nối PIT & Tiền Xử Lý (Tier F1xx)](#5-phân-tầng-3-quy-trình-bảo-đảm-toàn-vẹn-ghép-nối-pit--tiền-xử-lý-tier-f1xx)
   - [5.1. F101: Cổng Kiểm Định Toàn Vẹn Tham Chiếu Chéo (Cross-Dataset Validation Gate)](#51-f101-cổng-kiểm-định-toàn-vẹn-tham-chiếu-chéo-cross-dataset-validation-gate)
   - [5.2. F102: Động Cơ Hợp Nhất Phi Rò Rỉ Thời Gian (Point-In-Time Join Engine)](#52-f102-động-cơ-hợp-nhất-phi-rò-rỉ-thời-gian-point-in-time-join-engine)
   - [5.3. F103: Quy Trình 11 Kỹ Thuật Tiền Xử Lý & Kiểm Soát Chất Lượng Chuẩn Enterprise](#53-f103-quy-trình-11-kỹ-thuật-tiền-xử-lý--kiểm-soát-chất-lượng-chuẩn-enterprise)
   - [5.4. F104: Đóng Gói Đặc Trưng Học Máy & Phân Chia Tập Dữ Liệu Không Rò Rỉ](#54-f104-đóng-gói-đặc-trưng-học-máy--phân-chia-tập-dữ-liệu-không-rò-rỉ)
6. [Phân Tầng 4: Quy Trình Kiểm Định Thống Kê & Cổng Chống Quá Khớp (Tier F2xx)](#6-phân-tầng-4-quy-trình-kiểm-định-thống-kê--cổng-chống-quá-khớp-tier-f2xx)
   - [6.1. F201: Kiểm Định Giả Thuyết Hồi Quy Ngây Thơ (Naive Mean-Reversion Hypothesis Test)](#61-f201-kiểm-định-giả-thuyết-hồi-quy-ngây-thơ-naive-mean-reversion-hypothesis-test)
   - [6.2. F202: Sai Số Chuẩn Cụm Mã & Cụm Thời Gian (Cluster-Robust Standard Errors)](#62-f202-sai-số-chuẩn-cụm-mã--cụm-thời-gian-cluster-robust-standard-errors)
   - [6.3. F202b: Tỷ Số Sharpe Suy Giảm (DSR) & Nghịch Lý Khả Thi Giao Dịch (Tradeability Paradox)](#63-f202b-tỷ-số-sharpe-suy-giảm-dsr--nghịch-lý-khả-thi-giao-dịch-tradeability-paradox)
   - [6.4. F203: Ma Trận Kiểm Toán Chế Độ 2D & Rào Cản Đóng Cứng (Fail-Closed Circuit Breaker)](#64-f203-ma-trận-kiểm-toán-chế-độ-2d--rào-cản-đóng-cứng-fail-closed-circuit-breaker)
7. [Phân Tầng 5: Quy Trình NLP Đa Phương Thức & Nhất Quán Toán Học (Tier F3xx)](#7-phân-tầng-5-quy-trình-nlp-đa-phương-thức--nhất-quán-toán-học-tier-f3xx)
   - [7.1. F301: Tinh Chỉnh PhoBERT-base Căn Chỉnh Thị Hiếu Thị Trường (FinDPO)](#71-f301-tinh-chỉnh-phobert-base-căn-chỉnh-thị-hiếu-thị-trường-findpo)
   - [7.2. F302: Mạng Nơ-ron Hợp Nhất Đa Phương Thức Cross-Attention](#72-f302-mạng-nơ-ron-hợp-nhất-đa-phương-thức-cross-attention)
   - [7.3. F303: Tái Kiểm Định Đột Phá Alpha Đa Phương Thức](#73-f303-tái-kiểm-định-đột-phá-alpha-đa-phương-thức)
   - [7.4. F304: Cổng Giải Mã Ràng Buộc Tiên Đề Xác Suất Kolmogorov (HybridACD & V-FAN)](#74-f304-cổng-giải-mã-ràng-buộc-tiên-đề-xác-suất-kolmogorov-hybridacd--v-fan)
8. [Phân Tầng 6: Quy Trình Triển Khai Thực Tế, Giám Sát & Thích Ứng (Tier F4xx)](#8-phân-tầng-6-quy-trình-triển-khai-thực-tế-giám-sát--thích-ứng-tier-f4xx)
   - [8.1. F401: Dịch Vụ Suy Luận Trực Tuyến FastAPI Siêu Tốc (< 50ms)](#81-f401-dịch-vụ-suy-luận-trực-tuyến-fastapi-siêu-tốc--50ms)
   - [8.2. F402: Nhật Ký Đối Soát Lợi Nhuận Thực Tế & Giám Sát Trôi Dạt (Drift Monitor)](#82-f402-nhật-ký-đối-soát-lợi-nhuận-thực-tế--giám-sát-trôi-dạt-drift-monitor)
   - [8.3. F403: Tự Động Tái Huấn Luyện Liên Tục PEFT Fusion Head (< 25s)](#83-f403-tự-động-tái-huấn-luyện-liên-tục-peft-fusion-head--25s)
9. [Phân Tầng 7: Quy Trình Đấu Trường Mô Phỏng Chiến Lược Monte Carlo (Tier F5xx)](#9-phân-tầng-7-quy-trình-đấu-trường-mô-phỏng-chiến-lược-monte-carlo-tier-f5xx)
   - [9.1. F501: Đấu Trường Đa Bot & Bộ Mô Phỏng Vi Cấu Trúc Thị Trường Việt Nam](#91-f501-đấu-trường-đa-bot--bộ-mô-phỏng-vi-cấu-trúc-thị-trường-việt-nam)
10. [Phân Tầng 8: Quy Trình Hành Lang Pháp Lý, Quản Trị Rủi Ro & Sandbox (Tier F9xx)](#10-phân-tầng-8-quy-trình-hành-lang-pháp-lý-quản-trị-rủi-ro--sandbox-tier-f9xx)
   - [10.1. F901: Rào Cản Tuân Thủ Pháp Lý & Khóa Cứng Đặt Lệnh (Chỉ Thị UBCKNN 09/2023)](#101-f901-rào-cản-tuân-thủ-pháp-lý--khóa-cứng-đặt-lệnh-chỉ-thị-ubcknn-092023)
   - [10.2. F902: Hạ Tầng Định Tuyến Lệnh Giả Lập Sandbox (SSI / DNSE Paper Trading)](#102-f902-hạ-tầng-định-tuyến-lệnh-giả-lập-sandbox-ssi--dnse-paper-trading)
11. [Các Quy Trình Kiến Trúc & Vận Hành Bổ Trợ Đặc Thù](#11-các-quy-trình-kiến-trúc--vận-hành-bổ-trợ-đặc-thù)
   - [11.1. Concurrency Gate: Xử Lý Khóa Tệp CSDL DuckDB Trên Hệ Điều Hành Windows](#111-concurrency-gate-xử-lý-khóa-tệp-csdl-duckdb-trên-hệ-điều-hành-windows)
   - [11.2. Loop Engineering & CI/CD Regression Invariant Testing Suite](#112-loop-engineering--cicd-regression-invariant-testing-suite)
   - [11.3. Entity Resolution: Phân Giải Thực Thể Lãnh Đạo & Cổ Đông Lớn](#113-entity-resolution-phân-giải-thực-thể-lãnh-đạo--cổ-đông-lớn)
12. [Bảng So Sánh Trade-offs Giữa Các Giải Pháp Kỹ Thuật Đã Chọn](#12-bảng-so-sánh-trade-offs-giữa-các-giải-pháp-kỹ-thuật-đã-chọn)
13. [Đề Xuất Lộ Trình Tối Ưu Hóa & Khắc Phục Nhược Điểm (Actionable Roadmap)](#13-đề-xuất-lộ-trình-tối-ưu-hóa--khắc-phục-nhược-điểm-actionable-roadmap)

---

## 1. Lời Mở Đầu & Tôn Chỉ Kiểm Toán Hệ Thống

Trong quản trị kỹ thuật và phát triển hệ thống giao dịch định lượng (Quantitative Trading), việc chỉ nhìn vào các con số kiểm thử màu hồng (như tỷ lệ thắng hay Sharpe ratio cao) mà không đánh giá thấu đáo các nhược điểm, rủi ro tiềm ẩn và sự thỏa hiệp kỹ thuật (trade-offs) là con đường ngắn nhất dẫn đến thảm họa tài chính khi triển khai tiền thật.

Báo cáo này được lập nhằm mục đích: **Kiểm toán toàn diện và khách quan mọi mắt xích (All Processes) của hệ thống VESTA**, tổng hợp chi tiết:
- **Ưu điểm vượt trội (Pros):** Những đột phá phương pháp luận, bảo chứng toán học, tối ưu phần cứng và tính toàn vẹn dữ liệu đã đạt được.
- **Nhược điểm cốt tử (Cons):** Những hạn chế về dữ liệu, giả định toán học, rủi ro trượt giá, phụ thuộc hạ tầng mạng và chi phí tài nguyên phần cứng.
- **Cạm bẫy thực chiến (Pitfalls):** Những góc khuất có thể đánh lừa người vận hành nếu không có rào chắn tự động.
- **Lộ trình khắc phục (Remediation):** Các giải pháp kỹ thuật cụ thể để nâng cấp hệ thống trong các phiên bản tiếp theo.

---

## 2. Ma Trận Đánh Giá Tổng Hợp Ưu/Nhược Điểm Toàn Hệ Thống (Master Pros & Cons Matrix)

| Nhóm Quy Trình | Quy Trình Trọng Yếu | Ưu Điểm Đột Phá Lớn Nhất (Top Pros) | Nhược Điểm & Rủi Ro Lớn Nhất (Top Cons) | Mức Độ Rủi Ro (Risk Level) |
| :--- | :--- | :--- | :--- | :---: |
| **Tier F0xx (Core Crawlers)** | F000 - F009 | Phân tách 3 schema (`staging`, `core`, `meta`); tính bất biến lịch sử; độ phủ 100% nến ngày và BCTC 40+ quý. | API bên thứ 3 (vnstock) hay đổi cấu trúc; cào web HTML CafeF dễ vỡ khi đổi giao diện; bảng `balance_sheet` rỗng ở bản free. | **Trung bình** |
| **Tier F05x (Auxiliary Macro)** | F050 - F072 | Mở rộng 477k tin vĩ mô, 8 hiệp hội ngành, dòng vốn ngoại, báo cáo CTCK; 7 staging DBs cách ly hoàn toàn. | Phụ thuộc scrape web thô; 91.26% tin vĩ mô không có mã cổ phiếu; không thể merge trực tiếp vào `core.news`. | **Thấp** |
| **Tier F1xx (Integrity & PIT)** | F101 - F104 | Cắt phiên 15:00 triệt tiêu Look-ahead; 11 kỹ thuật (Winsorize, RankGauss, FFD $d=0.20$); 384k mẫu sạch 100%. | Giả định độ trễ nộp BCTC 30 ngày chỉ là xấp xỉ pháp lý; làm mịn dữ liệu có thể làm giảm biến động đột biến tự nhiên. | **Thấp** |
| **Tier F2xx (Hypothesis Gates)** | F201 - F203 | Kiểm định DSR & PBO chuẩn Bailey; bóc tách ngoại lai XDC; phát hiện 29 ô Sign-Flips khủng hoảng; rào chắn Fail-closed. | Giả thuyết bắt đáy hoàn toàn thất bại trong thị trường gấu; hiệu ứng suy giảm trên rổ HOSE ở $N \ge 2$ (Nghịch lý Khả thi). | **Cao** |
| **Tier F3xx (NLP & Consistency)** | F301 - F304 | Căn chỉnh FinDPO; Cross-Attention 128d (+50.8% Alpha); HybridACD Simplex-TCD (V-FAN 0.0197ms, Brier -29.51%). | PhoBERT tốn VRAM GPU; phụ thuộc chất lượng tiêu đề báo chí; 10 Checkers Kolmogorov mới chạy trên Negation. | **Trung bình** |
| **Tier F4xx (Production Serving)** | F401 - F403 | FastAPI streaming độ trễ P95 = 20.1ms (<50ms SLA); Dedup SimHash; EOD drift monitor; PEFT retrain <25s. | Chỉ đọc (read-only); bộ nhớ đệm RAM lưu sliding window; rủi ro quá tải nếu hàng ngàn bài báo dồn về cùng lúc. | **Thấp** |
| **Tier F5xx (Monte Carlo Arena)** | F501 | 10,000 đường đi mô phỏng vi cấu trúc VN ($T+2.5$, trần sàn $\pm 7\%$, phí thuế 0.25%); so tài 5 bot qua 5 kịch bản. | Mô hình bootstrap khối tĩnh không dự báo được sự thay đổi cấu trúc pháp lý mới; thanh khoản giả định là vô hạn trong biên độ. | **Trung bình** |
| **Tier F9xx (Compliance & Sandbox)**| F901 - F902 | Tuân thủ tuyệt đối Quy tắc B1; tôn trọng Công văn UBCKNN 09/2023; bảo vệ an toàn 100% vốn thật của nhà đầu tư. | Bị khóa cứng hoàn toàn; chưa thể thực chiến tự động tài khoản thật; phụ thuộc vào tiến độ cấp phép giao dịch thuật toán của KRX. | **Rất Thấp (An Toàn)** |

---

## 3. Phân Tầng 1: Quy Trình Thu Thập Dữ Liệu Lõi & Hạ Tầng CSDL (Tier F0xx)

### 3.1. F000: Môi Trường & Kiến Trúc CSDL DuckDB 3-Schema
- **Vai trò:** Khởi tạo hạ tầng lưu trữ lõi phân tách làm 3 schema: `staging` (vùng đệm), `core` (dữ liệu sạch đã xác thực), và `meta` (nhật ký theo dõi tiến độ).
- **Ưu điểm (Pros):**
  1. *Hiệu năng phân tích vượt trội:* DuckDB là CSDL hình cột (Columnar OLAP) nhúng trong tiến trình, tốc độ quét hàng triệu bản ghi nhanh gấp 10-50 lần so với SQLite hay PostgreSQL truyền thống.
  2. *Bảo vệ tính toàn vẹn (Zero Dirty Ingestion):* Không bao giờ ghi trực tiếp payload thô từ API vào bảng `core.*`. Mọi dữ liệu phải qua cổng hàm `promote.py`.
  3. *Truy vết trạng thái hạt nhân:* Bảng `meta.crawl_progress` ghi nhận chi tiết trạng thái từng mã cổ phiếu, mã lỗi HTTP và số lần thử lại.
- **Nhược điểm (Cons):**
  1. *Xung đột khóa tệp độc quyền trên Windows (`EXCLUSIVE_LOCK`):* DuckDB không hỗ trợ đa tiến trình đồng thời ghi vào một tệp CSDL trên hệ điều hành Windows, dễ gây lỗi `IOException: Could not set lock on file`.
  2. *Bộ nhớ RAM có thể phình to:* Khi thực hiện các câu truy vấn kết nối (JOIN) phức tạp trên hàng triệu dòng nến mà không giới hạn `PRAGMA threads` hoặc `memory_limit`, DuckDB có thể chiếm dụng RAM đột biến.
- **Khuyến nghị & Cạm bẫy:** Tách luồng cào dữ liệu sang file đệm `vesta_staging.duckdb`, sau đó thực hiện giao dịch nạp nguyên tử (Atomic Ingestion) vào `vesta.duckdb`.

### 3.2. F001 & F001b: Quản Lý Master Data Danh Bạ Cổ Phiếu & Đối Soát CafeF
- **Vai trò:** Xây dựng danh bạ toàn bộ 3,446 mã chứng khoán (HOSE, HNX, UPCOM, Hủy niêm yết, OTC) làm trục tham chiếu cho toàn bộ hệ thống.
- **Ưu điểm (Pros):**
  1. *Triệt tiêu thiên vị sống sót (Survivorship Bias Guard):* Thu nạp cả các mã đã hủy niêm yết và tạm ngừng giao dịch, ngăn chặn sai lệch thuật toán chỉ học trên các cổ phiếu chiến thắng.
  2. *Phát hiện chính xác phân khúc sàn:* Ánh xạ đúng mã `CenterId` của CafeF (1: HOSE, 2: HNX/HASTC, 8: OTC, 9: UPCOM), bổ sung 984 doanh nghiệp OTC mà vnstock bỏ sót.
- **Nhược điểm (Cons):**
  1. *Cột `delisted_date` thiếu hụt từ nguồn miễn phí:* Nguồn API vnstock không cung cấp ngày hủy niêm yết chuẩn xác cho toàn bộ các mã quá khứ, buộc phải chấp nhận giá trị `NULL` có kiểm soát.
  2. *Thay đổi mã chứng khoán & Chuyển sàn:* Chưa có cơ chế tự động theo dõi lịch sử chuyển sàn (ví dụ từ UPCOM lên HOSE) theo chuỗi thời gian liên tục mà chỉ lưu trạng thái hiện tại.
- **Khuyến nghị:** Xây dựng bảng thứ cấp `core.symbol_exchange_history` để ghi nhận ngày chuyển sàn chính xác.

### 3.3. F002: Thu Thập & Xác Thực Nến Ngày OHLCV Toàn Thị Trường
- **Vai trò:** Thu thập toàn bộ 5.18 triệu thanh nến giao dịch lịch sử từ năm 2000 đến nay cho toàn bộ cổ phiếu.
- **Ưu điểm (Pros):**
  1. *Bảo toàn tính bất biến (Idempotent Upsert):* Chạy lại nhiều lần không sinh ra dòng trùng lặp nhờ khóa kết hợp `(symbol, time)`.
  2. *Rào chắn hình học nến:* Kiểm định chặt chẽ tính hợp lý của giá ($Low \le Open, Close \le High$), loại bỏ ngay các thanh nến lỗi từ nguồn cấp.
  3. *Lưu trữ giá gốc chưa điều chỉnh (Raw Close):* Tách biệt hoàn toàn giá gốc và hệ số quyền doanh nghiệp, tránh làm biến dạng chuỗi thời gian khi có sự kiện chia tách mới.
- **Nhược điểm (Cons):**
  1. *Khoảng trống thanh khoản (Zero-Volume Bars):* Chiếm tới 29.1% tổng số thanh nến trên sàn UPCOM và HNX do các mã rác không có giao dịch, dễ tạo ra các tỷ suất sinh lời giả lập 0.0%.
  2. *Thiếu dữ liệu điều chỉnh giá tự động:* Do vnstock không cung cấp chuỗi giá đã điều chỉnh chính thức, hệ thống phải tự tính hệ số qua F006 và F009.
- **Khuyến nghị:** Bắt buộc áp dụng bộ lọc `volume > 0` và giá trị giao dịch tối thiểu trước khi đưa vào mô hình học máy.

### 3.4. F003: Thu Thập Tin Tức vnstock API
- **Vai trò:** Thu thập luồng tin tức tài chính theo mã chứng khoán thông qua API của gói vnstock.
- **Ưu điểm (Pros):**
  1. *Dữ liệu có cấu trúc cao:* Trả về trực tiếp JSON với các trường chuẩn hóa: tiêu đề, tóm tắt, thời gian công bố, nguồn phát hành.
  2. *Tích hợp sẵn mã cổ phiếu:* Tin tức đã được bên thứ 3 gắn sẵn mã doanh nghiệp, giảm chi phí nhận diện thực thể (Entity Extraction).
- **Nhược điểm (Cons):**
  1. *Độ tin cậy hạ tầng thấp:* Endpoint API tin tức của vnstock thường xuyên trả về mã lỗi HTTP 500 hoặc ngắt kết nối đột ngột.
  2. *Không có lịch sử sâu:* API chỉ cho phép lấy một số lượng trang cố định gần nhất, không thể cào ngược về các năm 2010-2015.
- **Khuyến nghị:** Dùng vnstock News làm nguồn bổ trợ EOD; chuyển trọng tâm dữ liệu lịch sử sang bộ cào CafeF (F004).

### 3.5. F004, F004b & F004c: Bóc Tách Toàn Văn Báo Chí & Điều Phối CafeF
- **Vai trò:** Cào độc lập toàn bộ kho lưu trữ tin tức tài chính khổng lồ của CafeF từ năm 2007 đến nay, trích xuất toàn văn (Body Content) và điều phối chuyên mục.
- **Ưu điểm (Pros):**
  1. *Kho dữ liệu khổng lồ:* Đã thu nạp hơn 669,000 bài báo tài chính tiếng Việt, tạo thành kho ngữ liệu vô giá cho NLP tài chính.
  2. *Bóc tách toàn văn chất lượng cao (F004b):* Phân tích selector `div.detail-content`, loại bỏ sạch sẽ quảng cáo, bài viết liên quan và boilerplate HTML; độ dài bài báo đạt 1,500 - 8,000 ký tự.
  3. *Lọc thực thể chặt chẽ (F004c):* Áp dụng cú pháp định danh nghiêm ngặt (`cổ phiếu {TICKER}`, `mã CK {TICKER}`), loại bỏ hoàn toàn các từ viết tắt gây nhiễu (CEO, TP.HCM, USD, SJC, CIA, SME, ABS, VIP).
- **Nhược điểm (Cons):**
  1. *Nguy cơ bị chặn IP (Rate Limiting/Anti-Scraping):* Cào HTML quy mô lớn có thể kích hoạt tường lửa Cloudflare hoặc Captcha của nhà mạng.
  2. *Thời gian cào kéo dài:* Do phải tôn trọng `robots.txt` và độ trễ lịch sự (`crawl_delay = 1.0s`), việc cào toàn bộ lịch sử mất từ 2 đến 3 ngày liên tục.
- **Khuyến nghị:** Duy trì kết nối Connection Pooling, xoay vòng User-Agent và lưu trữ tệp HTML thô vào thư mục archive để tái phân tích khi cần.

### 3.6. F004d: Động Cơ Gắn Thẻ Ngành & Phân Loại Taxonomy ICB
- **Vai trò:** Ánh xạ các bài báo phân tích vĩ mô và ngành vào danh mục 25 ngành chuẩn ICB và các mã cổ phiếu liên đới.
- **Ưu điểm (Pros):**
  1. *Quy tắc Fail-closed 2 tầng (2-Tier Guardrail):* Tầng A bắt buộc phải có từ khóa neo ngữ cảnh thị trường (`cổ phiếu`, `nhóm ngành`, `dòng tiền`), loại bỏ 100% các tin tức hành chính dân sự gây nhiễu.
  2. *Triệt tiêu hiện tượng phình to dữ liệu (Zero Raw Fan-Out):* Không nhân bản bài báo vào bảng `core.news`, mà lưu trữ liên kết vào bảng quan hệ `core.sector_news_signal`.
- **Nhược điểm (Cons):**
  1. *Phân tích dựa trên từ khóa tĩnh:* Chưa nhận diện được ngữ cảnh đảo nghĩa phức tạp nếu bài báo đề cập đa ngành đối lập nhau.
  2. *Tỷ lệ khớp lệnh còn thấp:* Chỉ khoảng 1.36% bài báo vĩ mô đạt đủ tiêu chuẩn khắt khe để chuyển hóa thành tín hiệu ngành.
- **Khuyến nghị:** Nâng cấp từ điển từ khóa sang mô hình embedding ngữ nghĩa (Sentence-BERT tiếng Việt) trong giai đoạn tiếp theo.

### 3.7. F005: Bộ Thu Thập Báo Cáo Tài Chính 5 Bảng Kế Toán VAS
- **Vai trò:** Thu thập đầy đủ 5 báo cáo tài chính quý: Bảng CĐKT, Kết quả kinh doanh, Lưu chuyển tiền tệ, Tỷ số tài chính, Điểm sức khỏe doanh nghiệp.
- **Ưu điểm (Pros):**
  1. *Xử lý triệt để cấu trúc dữ liệu xoay trục (Melt Pivoted Schema):* Tự động unpivot bảng dữ liệu từ dạng ngang (cột là quý) sang dạng dọc chuẩn hoá, đóng gói các chỉ tiêu kế toán vào JSON metric blob.
  2. *Thiết lập độ trễ luật định chống Look-ahead (Statutory Lag):* Tự động cộng 30 ngày vào ngày kết thúc quý theo quy định Thông tư 96/2020/TT-BTC làm mốc khả dụng (`available_at`).
  3. *Lưu trữ bất biến lịch sử sửa đổi (Revision-Proof):* Khóa chính bao gồm cả `fetched_at`, bảo tồn nguyên vẹn các lần doanh nghiệp đính chính BCTC sau kiểm toán.
- **Nhược điểm (Cons):**
  1. *Lỗ hổng Bảng Cân Đối Kế Toán ở bản miễn phí:* vnstock bản cộng đồng trả về rỗng đối với bảng `balance_sheet`, tạo ra khoảng trống dữ liệu phải bù đắp từ CafeF.
  2. *Sai lệch ngày công bố thực tế:* Độ trễ cố định 30 ngày chỉ là mức bình quân luật định; trên thực tế một số doanh nghiệp công bố sớm (ngày 20) hoặc xin gia hạn (ngày 45).
- **Khuyến nghị:** Tích hợp trực tiếp ngày công bố thực tế từ chuyên mục công bố thông tin của Sở giao dịch để thay thế cho mốc ước lượng 30 ngày.

### 3.8. F006: Thu Thập Sự Kiện Doanh Nghiệp & Lịch Quyền
- **Vai trò:** Cào lịch sự kiện chia cổ tức, thưởng cổ phiếu, phát hành riêng lẻ, đại hội cổ đông và giao dịch của cổ đông nội bộ/cổ đông lớn.
- **Ưu điểm (Pros):**
  1. *Bao phủ toàn diện các loại sự kiện:* Thu nạp hơn 40,277 sự kiện, phân loại thành các nhóm danh mục chuẩn hóa: `DIVIDEND`, `SHAREHOLDER_MEETING`, `MAJOR_SHAREHOLDER_TRADING`.
  2. *Lưu trữ JSON chi tiết (detail_json):* Giữ nguyên tỷ lệ chi trả cổ tức (ví dụ: 10:1 hoặc 15% tiền mặt), phục vụ việc tính toán hệ số điều chỉnh giá.
- **Nhược điểm (Cons):**
  1. *Định dạng văn bản tự do trong trường ghi chú:* Một số sự kiện ghi tỷ lệ bằng chuỗi tự nhiên phức tạp (ví dụ: "trả cổ tức đợt 2 năm 2023 bằng tiền tỷ lệ 7.5%"), đòi hỏi biểu thức chính quy (Regex) tinh vi để trích xuất số học.
- **Khuyến nghị:** Xây dựng module chuẩn hóa tỷ lệ toán học (`extract_cash_and_stock_ratio()`) để tự động hóa hoàn toàn phép tính hệ số pha loãng.

### 3.9. F007 & F007b: Snapshot Bảng Giá Thời Gian Thực & Thăm Dò Sponsor Tier
- **Vai trò:** Thu thập ảnh chụp bảng giá thời gian thực (82 cột MultiIndex) từ VCI và khảo sát tính năng nâng cao của gói tài trợ vnstock_data Silver Sponsor.
- **Ưu điểm (Pros):**
  1. *Độ sâu thông tin vi mô (Microstructure Breadth):* 82 cột dữ liệu phản ánh đầy đủ 3 mức giá dư mua/dư bán tốt nhất, khối lượng khớp lệnh chủ động và room ngoại.
  2. *Chính sách lưu trữ tích lũy (ACCUMULATE Policy):* Không bao giờ ghi đè; mỗi lần chụp tạo ra một bản ghi độc lập có gắn timestamp microsecond, sẵn sàng cho phân tích dòng tiền trong phiên.
  3. *Khám phá API tài trợ (F007b):* Xác minh thực tế các endpoint `Insights`, `Screener`, `Sentiment` với hạn mức 300 req/min.
- **Nhược điểm (Cons):**
  1. *Dung lượng cơ sở dữ liệu tăng nhanh:* Nếu chụp bảng giá liên tục 1 phút/lần cho 1,700 mã, CSDL sẽ phình to hàng trăm megabyte mỗi phiên.
  2. *Phụ thuộc vào khóa bản quyền Sponsor:* Nếu API key hết hạn hoặc lỗi kết nối mạng, tiến trình chụp dữ liệu thời gian thực sẽ bị đình trệ.
- **Khuyến nghị:** Chỉ bật chế độ chụp Snapshot tần suất cao trong khung giờ khớp lệnh liên tục (09:15 - 11:30 và 13:00 - 14:30) cho rổ cổ phiếu VN30 và VN100.

### 3.10. F008 & F009: Cơ Chế Bù Lỗi Tự Động & Chốt Chặn Kiểm Toán F0xx
- **Vai trò:** Khung điều phối bù lỗi tự động bằng thuật toán lùi số mũ (Exponential Backoff) và kiểm toán toàn diện tính toàn vẹn của phân tầng F0xx.
- **Ưu điểm (Pros):**
  1. *Khả năng tự phục hồi (Self-Healing Resiliency):* Tự động phát hiện lỗi mạng tạm thời (HTTP 429, 502, 504) và lập lịch thử lại theo công thức $t = 1.5 \times 2^k$, phân biệt rõ ràng giữa lỗi mạng và dữ liệu rỗng vĩnh viễn.
  2. *Kiểm toán độc lập không thỏa hiệp (F009 Audit Gate):* Phát hiện và đảo ngược các số liệu giả lập, vá triệt để lỗ hổng rò rỉ Look-ahead trong bảng `core.fundamentals`, thiết lập quy ước giữ nguyên payload gốc (`conventions.md`).
- **Nhược điểm (Cons):**
  1. *Tốn thời gian chờ khi số lượng job lỗi lớn:* Nếu API bên ngoài sập diện rộng, hàng ngàn job thử lại có thể làm nghẽn hàng đợi tiến trình nền.
- **Khuyến nghị:** Thiết lập cơ chế ngắt mạch tổng (Global Circuit Breaker): Tạm dừng toàn bộ pipeline nếu tỷ lệ lỗi liên tiếp vượt quá 30% trong 5 phút.

---

## 4. Phân Tầng 2: Quy Trình Thu Thập Dữ Liệu Vĩ Mô, Bổ Trợ & Thể Chế (Tier F05x)

### 4.1. F050: Thu Thập Chuỗi Chỉ Số Thị Trường Lịch Sử
- **Ưu điểm:** Cung cấp đầy đủ chuỗi giá lịch sử của VN-Index, VN30, HNX-Index, UPCOM-Index từ năm 2000; đây là biến số sống còn để xác định chế độ thị trường (Regime) và đường xu hướng EMA 200 ngày.
- **Nhược điểm:** Dữ liệu chỉ số của sàn UPCOM trong những năm đầu mới thành lập (2009-2012) có thanh khoản rất mỏng, độ biến động không phản ánh đúng cung cầu tự nhiên.
- **Khuyến nghị:** Chỉ sử dụng VN-Index và VN30 làm đại diện cho chế độ thanh khoản toàn thị trường.

### 4.2. F051: Thu Thập Dòng Tiền Khối Ngoại & Room Sở Hữu
- **Ưu điểm:** Thu nạp 63,197 dòng giao dịch mua/bán ròng và tỷ lệ sở hữu nước ngoài; loại bỏ hoàn toàn các cột giá trị tiền giả lập, chỉ giữ lại khối lượng thực tế tuân thủ Quy tắc B3/B4.
- **Nhược điểm:** Chưa bóc tách được giao dịch khớp lệnh trực tiếp trên sàn (Order Matching) so với giao dịch thỏa thuận đột biến (Put-through) của các quỹ ngoại lớn.
- **Khuyến nghị:** Tách bạch dữ liệu thỏa thuận để tránh tín hiệu dòng tiền ngoại bị méo mó cục bộ.

### 4.3. F052 & F053: Vá Lỗ Hổng BCTC & Điều Phối Lô Thanh Khoản
- **Ưu điểm:** Khắc phục thành công lỗ hổng thiếu bảng cân đối kế toán từ vnstock bằng cách cào trực tiếp từ API của CafeF; điều phối ưu tiên cho các mã thanh khoản cao trong rổ VN30 và Midcap.
- **Nhược điểm:** Trạng thái hiện tại vẫn đang bị đánh dấu `blocked/not_started` trong backlog do sự không đồng nhất về mã định danh tài khoản giữa chuẩn tiếng Việt của CafeF và chuẩn mã số của vnstock.
- **Khuyến nghị:** Hoàn thiện bảng ánh xạ tương đương (Mapping Table) giữa chỉ tiêu tài chính CafeF và vnstock để tháo gỡ điểm nghẽn F052.

### 4.4. F054: Bóc Tách Báo Cáo Phân Tích Doanh Nghiệp CTCK
- **Ưu điểm:** Khai thác dữ liệu định giá chuyên sâu, giá mục tiêu và khuyến nghị (Mua/Bán/Khả quan) từ các CTCK hàng đầu (SSI, HSC, VCSC, VNDirect).
- **Nhược điểm:** Định dạng báo cáo chủ yếu là file PDF phức tạp, đòi hỏi bộ trích xuất OCR/PDF Parser tốn tài nguyên và dễ lỗi định dạng bảng biểu.
- **Khuyến nghị:** Chỉ bóc tách phần tóm tắt khuyến nghị và giá mục tiêu từ tiêu đề và trang bìa đầu tiên của báo cáo.

### 4.5. F055 & F056: Tin Tức Vĩ Mô Vietstock & Dữ Liệu World Bank Open Data
- **Ưu điểm:** Thu nạp 477,733 bản ghi tin tức vĩ mô, tiền tệ, hàng hóa và chuỗi thời gian các chỉ số kinh tế vĩ mô chuẩn quốc tế của Việt Nam (GDP, CPI, FDI, Cán cân thanh toán) qua REST API công khai của World Bank.
- **Nhược điểm:** Tần suất công bố dữ liệu World Bank theo năm hoặc quý, có độ trễ lớn so với nhịp giao dịch hàng ngày của thị trường chứng khoán.
- **Khuyến nghị:** Sử dụng dữ liệu World Bank cho phân tích chu kỳ kinh tế dài hạn; dùng dữ liệu Vietstock cho biến động tin tức ngắn hạn.

### 4.6. F057, F058 & F059: Cơ Quan Quản Lý & Pháp Quy (NHNN, Báo Chính Phủ, UBCKNN)
- **Ưu điểm:** Thu thập trực tiếp nguồn văn bản quy phạm pháp luật gốc: quyết định điều hành lãi suất của NHNN, nghị quyết tháo gỡ khó khăn kinh tế của Chính phủ, và 22,878 quyết định xử phạt thao túng giá của UBCKNN.
- **Nhược điểm:** Trang web cơ quan quản lý nhà nước thường xuyên bảo trì, đổi giao diện, hoặc tốc độ phản hồi máy chủ rất chậm trong giờ hành chính.
- **Khuyến nghị:** Lập lịch cào vào ban đêm (từ 01:00 đến 04:00 sáng) với cơ chế timeout linh hoạt (tối thiểu 30 giây).

### 4.7. F060 - F063: Báo Chí Tài Chính Chuyên Sâu (VnEconomy, TNCK, Đầu Tư, Ngân Hàng)
- **Ưu điểm:** Ngữ liệu báo chí chính luận có độ tin cậy và chiều sâu phân tích kinh tế cao hơn hẳn các diễn đàn mạng xã hội; tôn trọng tuyệt đối `robots.txt` với độ trễ 1.0s.
- **Nhược điểm:** Nội dung bài viết mang tính phân tích đa chiều, thường xuất hiện nhiều ý kiến trái ngược nhau trong cùng một bài, gây khó khăn cho việc phân loại nhãn cảm xúc đơn nhất.
- **Khuyến nghị:** Áp dụng kỹ thuật phân đoạn đoạn văn (Paragraph Chunking) và chấm điểm cảm xúc theo từng thực thể doanh nghiệp được nhắc tới.

### 4.8. F064 - F071: 8 Bộ Thu Thập Dữ Liệu Hiệp Hội Ngành & Chuỗi Giá Trị
- **Ưu điểm:** Đi sâu vào dữ liệu ngách của từng chuỗi giá trị: giá thép/điện (MOIT), kim ngạch xuất khẩu tôm cá (VASEP), pháp lý dự án địa ốc (HoREA), giá phân bón (Hội Nông dân), thuế tiêu thụ rượu bia (VBA).
- **Nhược điểm:** Các trang web hiệp hội ngành thường được xây dựng trên nền tảng web cũ, không có cấu trúc HTML chuẩn mực, dữ liệu cập nhật không đều đặn theo tuần.
- **Khuyến nghị:** Thiết lập cơ chế giám sát thay đổi mã hash trang chủ để chỉ cào khi phát hiện có bài viết mới.

### 4.9. F072: Hợp Nhất 7 Staging Database & Kiểm Toán Khóa Ngoại Vĩ Mô
- **Ưu điểm:** Đã kiểm toán toàn bộ 477,733 bài báo vĩ mô; đưa ra quyết định kiến trúc sáng suốt: **Bác bỏ việc gộp vật lý vào bảng `core.news`** vì 91.26% tin vĩ mô không gắn với mã cổ phiếu cụ thể, nếu ép buộc sẽ làm nổ ràng buộc khóa chính `symbol NOT NULL` và sinh ra 436k dòng rác trong bảng ghép nối PIT.
- **Nhược điểm:** Các bài báo vĩ mô hiện phải truy xuất qua view ảo (`core.v_all_news`), làm tăng độ phức tạp khi viết câu truy vấn phân tích tổng hợp.
- **Khuyến nghị:** Xây dựng bảng quan hệ chuyên biệt `core.macro_events` để liên kết tin vĩ mô với chỉ số VN-Index thay vì cố gắng gắn vào từng cổ phiếu riêng lẻ.

---

## 5. Phân Tầng 3: Quy Trình Bảo Đảm Toàn Vẹn, Ghép Nối PIT & Tiền Xử Lý (Tier F1xx)

### 5.1. F101: Cổng Kiểm Định Toàn Vẹn Tham Chiếu Chéo (Cross-Dataset Validation Gate)
- **Vai trò:** Trạm kiểm soát chất lượng dữ liệu đa tầng trước khi bước vào giai đoạn nghiên cứu mô hình.
- **Ưu điểm (Pros):**
  1. *Nguyên tắc Fail-closed tuyệt đối:* Bất kỳ sự xuất hiện nào của mã mồ côi (không nằm trong `dim_symbol`), nến giá vi phạm hình học ($Low > High$), hoặc mốc thời gian tương lai (`fetched_at > current_timestamp`) đều lập tức ném ra ngoại lệ `ValidationError` và dừng toàn bộ pipeline.
  2. *Bao phủ toàn diện 7 bảng lõi:* Tự động quét kiểm tra trên hàng triệu dòng dữ liệu chỉ trong vài chục giây nhờ tối ưu hóa câu lệnh SQL trong DuckDB.
- **Nhược điểm (Cons):**
  1. *Khắt khe quá mức với dữ liệu lịch sử cũ:* Một số mã cổ phiếu OTC hoặc giải thể từ giai đoạn 2005-2008 có thể bị thiếu một vài trường phụ, khiến cổng kiểm định dừng hoạt động nếu không có cơ chế bỏ qua ngoại lệ được phê duyệt.
- **Khuyến nghị:** Phân loại cảnh báo thành hai cấp: `CRITICAL_ERROR` (dừng pipeline) và `WARNING_FLAG` (ghi nhật ký để kiểm tra thủ công).

### 5.2. F102: Động Cơ Hợp Nhất Phi Rò Rỉ Thời Gian (Point-In-Time Join Engine)
- **Vai trò:** Ghép nối tin tức, giá giao dịch và báo cáo tài chính đúng thời điểm lịch sử xuất hiện thông tin, tính toán lợi nhuận tương lai $T+1, T+5, T+30$.
- **Ưu điểm (Pros):**
  1. *Triệt tiêu 100% Look-ahead Bias:*
     - Áp dụng mốc cắt giờ thị trường đóng cửa (15:00): Tin tức công bố sau 15:00 bắt buộc phải lấy giá mở cửa của phiên $T+1$ kế tiếp làm điểm bắt đầu, tuyệt đối không được dùng giá đóng cửa phiên $T+0$.
     - Ghép nối BCTC bằng hàm `get_as_of()`: Tại thời điểm tháng 02/2023 chỉ được nhìn thấy BCTC Quý 3/2022 đã công bố, không bao giờ được nhìn thấy BCTC Quý 4/2022 dù cùng niên độ.
  2. *Lợi nhuận tính theo ngày giao dịch thực tế (Trading Days):* Các mốc $T+1, T+5, T+30$ được tính dựa trên chuỗi ngày giao dịch có nến thực tế, loại trừ hoàn toàn các ngày cuối tuần, nghỉ lễ Tết.
- **Nhược điểm (Cons):**
  1. *Vấn đề tin tức có mốc giờ bị làm tròn (Midnight Timestamps):* Phát hiện 25.6% bài báo cũ có mốc giờ công bố bị nhà mạng lưu mặc định là `00:00:00`. Nếu coi đây là tin trước giờ mở cửa có thể gây sai lệch nhẹ.
  2. *Hiện tượng giá bằng không (Zero Price Trap):* 1,038 sự kiện xuất hiện mức giá 0 do cổ phiếu mất thanh khoản hoặc ngừng giao dịch, có thể gây lỗi chia cho không (`ZeroDivisionError`) nếu không có bộ lọc bảo vệ.
- **Khuyến nghị:** Đối với các tin tức có giờ `00:00:00`, tự động gán nhãn độ trễ chuyển sang phiên giao dịch kế tiếp để đảm bảo tính an toàn phòng thủ.

### 5.3. F103: Quy Trình 11 Kỹ Thuật Tiền Xử Lý & Kiểm Soát Chất Lượng Chuẩn Enterprise
- **Vai trò:** Bộ công cụ tiền xử lý dữ liệu định lượng chuyên sâu bậc nhất, đạt chuẩn mực của các quỹ đầu tư định lượng phố Wall.
- **Ưu điểm (Pros):**
  1. *Khử ngoại lai thao túng XDC:* Phát hiện và cô lập sự kiện cổ phiếu XDC tăng phi lý +3,021% trên sàn UPCOM, kéo Kurtosis từ mức báo động **4,355** xuống mức chuẩn hóa **7.82**, Skewness từ 17.2 về 1.21.
  2. *Winsorization hai đầu [0.5%, 99.5%]:* Cắt tỉa các đột biến đuôi dày nhưng vẫn giữ nguyên số lượng mẫu quan sát.
  3. *Chuẩn hóa phi tham số RankGauss ($N(0, 1)$):* Chuyển đổi các chỉ số tài chính kế toán bị lệch nặng (P/E, P/B, ROE) về phân phối chuẩn Gauss, giúp các mạng nơ-ron học sâu hội tụ ổn định và không bị bão hòa hàm kích hoạt.
  4. *Vi phân phân số (Fractional Differentiation - FFD $d=0.20$):* Đạt được tính dừng thống kê (Stationarity - kiểm định ADF $p < 0.01$) nhưng vẫn lưu giữ tối đa hơn 80% bộ nhớ dài hạn của chuỗi giá gốc.
  5. *Mã hóa Gray Code cho Regime & Exchange:* Khoảng cách Hamming giữa các trạng thái liền kề luôn bằng 1, giúp biểu diễn không gian liên tục mượt mà cho mạng nơ-ron.
  6. *Khử trùng lặp SimHash 64-bit:* Nhận diện và gộp các bài báo syndicated cùng nội dung xuất hiện trên nhiều báo khác nhau trong vòng 6 giờ.
- **Nhược điểm (Cons):**
  1. *Độ phức tạp tính toán cao:* Việc tính toán vi phân phân số FFD với cửa sổ lịch sử dài trên hàng ngàn mã cổ phiếu đòi hỏi thời gian xử lý ban đầu đáng kể.
  2. *Làm mịn dữ liệu có thể làm mất tín hiệu đột biến hiếm:* Winsorize có thể làm giảm bớt mức độ nghiêm trọng của một số cuộc khủng hoảng thanh khoản thực tế.
- **Khuyến nghị:** Lưu trữ sẵn các đặc trưng đã tính FFD và RankGauss vào file Parquet định dạng nhị phân (`data/train_matrix.parquet`) để tái sử dụng tức thì.

### 5.4. F104: Đóng Gói Đặc Trưng Học Máy & Phân Chia Tập Dữ Liệu Không Rò Rỉ
- **Vai trò:** Xuất bản tập dữ liệu đa phương thức hoàn chỉnh gồm 384,431 bản ghi phục vụ huấn luyện các mô hình AI.
- **Ưu điểm (Pros):**
  1. *Phân chia thời gian thanh lọc nghiêm ngặt (Purged Temporal Split):* Chia tách tập mẫu theo mốc năm tuyệt đối: Tập Train (< 2024, 70%), Tập Val (2024, 15%), Tập Test ngoài mẫu OOS ($\ge$ 2025, 15%). Tuyệt đối không xáo trộn ngẫu nhiên (No Random Shuffle), loại bỏ 100% rò rỉ thông tin tương lai vào quá khứ.
  2. *Đóng gói đa phương thức hoàn chỉnh:* Mỗi bản ghi tích hợp đồng thời vector biểu diễn văn bản, 24 chỉ số kế toán RankGauss và 128 chiều nhúng trạng thái vĩ mô.
- **Nhược điểm (Cons):**
  1. *Mất cân bằng nhãn phân lớp:* Nhãn trung tính (Neutral) chiếm hơn 91% tổng số sự kiện tin tức, trong khi nhãn tiêu cực chỉ chiếm ~4% và tích cực chiếm ~5%, gây khó khăn cho việc tối ưu hàm mất mát phân loại thông thường.
- **Khuyến nghị:** Áp dụng hàm mất mát Focal Loss hoặc kỹ thuật gán trọng số lớp nghịch đảo (Inverse Class Weighting) khi huấn luyện mô hình sâu.

---

## 6. Phân Tầng 4: Quy Trình Kiểm Định Thống Kê & Cổng Chống Quá Khớp (Tier F2xx)

### 6.1. F201: Kiểm Định Giả Thuyết Hồi Quy Ngây Thơ (Naive Mean-Reversion Hypothesis Test)
- **Vai trò:** Kiểm định khoa học giả thuyết sơ khởi: "Cổ phiếu sau khi bị giảm giá vì tin tức tiêu cực ở ngày $T+5$ sẽ có xu hướng hồi phục ở ngày $T+30$".
- **Ưu điểm (Pros):**
  1. *Ý nghĩa thống kê ban đầu rất cao:* Kiểm định Student's t-test cặp đôi trên 15,081 sự kiện tin tiêu cực cho kết quả $t = 6.84, p = 8.39 \times 10^{-12}$, chênh lệch lợi nhuận trung bình đạt $+1.8745\%$, quy mô tác động Cohen's $d = 0.0557$.
  2. *Bộ từ điển tài chính minh bạch:* Sử dụng từ điển phân loại phân cực tài chính tiếng Việt đơn giản, chạy nhanh và có tính tái lập bit-identical 100%.
- **Nhược điểm (Cons):**
  1. *Cạm bẫy giá trị trung bình số học (Arithmetic Mean Illusion):* Con số trung bình $+1.87\%$ thực chất bị chi phối bởi một số cổ phiếu penny vốn hóa siêu nhỏ tăng giá bằng lần ở UPCOM.
  2. *Tỷ lệ thắng thực tế thấp:* Tỷ lệ thắng (Win Rate) thực tế chỉ đạt **44.10%** (tỷ lệ thua lên tới 48.28%), cho thấy phần lớn các trường hợp bắt đáy đều không mang lại lợi nhuận như kỳ vọng số học.
- **Khuyến nghị:** Không bao giờ đưa ra quyết định giải ngân chỉ dựa trên giá trị kỳ vọng trung bình; bắt buộc phải kết hợp tỷ lệ thắng trung vị (Median Win Rate).

### 6.2. F202: Sai Số Chuẩn Cụm Mã & Cụm Thời Gian (Cluster-Robust Standard Errors)
- **Vai trò:** Kiểm toán tính độc lập của các quan sát mẫu, loại trừ hiện tượng tự tương quan chuỗi thời gian và tương quan chéo giữa các doanh nghiệp cùng ngành.
- **Ưu điểm (Pros):**
  1. *Kỹ thuật Bootstrap hai chiều chuẩn mực:* Thực hiện tái lấy mẫu theo cụm doanh nghiệp (1,437 cụm, $z = 5.98, p = 2.25 \times 10^{-9}$) và theo cụm tháng lịch sử (214 cụm, $z = 3.12, p = 0.00184$).
  2. *Khẳng định hiệu ứng không bị thao túng bởi một vài mã cá biệt:* Khoảng tin cậy 95% sau tái lấy mẫu hoàn toàn loại trừ số 0, chứng minh hiện tượng đảo chiều có tính quy luật trên diện rộng.
- **Nhược điểm (Cons):**
  1. *Phát hiện tính bất đồng nhất nghiêm trọng (Regime Heterogeneity):* Kiểm tra lịch sử chỉ ra hiệu ứng đảo chiều chỉ đúng trong một số giai đoạn nhất định và bị đảo dấu âm trong các giai đoạn khác.
- **Khuyến nghị:** Coi F202 là điều kiện cần; bắt buộc phải bước qua cổng F202b và F203 trước khi chấp nhận tín hiệu.

### 6.3. F202b: Tỷ Số Sharpe Suy Giảm (DSR) & Nghịch Lý Khả Thi Giao Dịch (Tradeability Paradox)
- **Vai trò:** Áp dụng phương pháp luận của Bailey & López de Prado (2014) để khấu trừ số lượng thử nghiệm $N$, tính toán xác suất quá khớp mô hình (PBO).
- **Ưu điểm (Pros):**
  1. *Xác suất Overfitting cực thấp:* Phương pháp CSCV PBO trên 16 khối dữ liệu cho kết quả **PBO = 0.007 (0.7% << 50%)**, chứng minh chiến lược không bị quá khớp dữ liệu quá khứ.
  2. *Đạt chuẩn DSR toàn thị trường:* Toàn thị trường sau khi Winsorize đạt $DSR > 0.96$ ở mọi số lượng thử nghiệm $N \in [1, 2, 3]$.
  3. *Phát hiện "Nghịch lý Khả thi Giao dịch" (Tradeability Paradox):* Bóc trần sự thật rằng riêng rổ cổ phiếu lớn HOSE **thất bại hoàn toàn ở $N \ge 2$** ($DSR = 0.945$ ở $N=2$ và $0.892$ ở $N=3$).
- **Nhược điểm (Cons):**
  1. *Cảnh báo đỏ cho khả năng mở rộng quy mô vốn (Scalability Trap):* Hiệu ứng đảo chiều tâm lý chủ yếu tồn tại ở nhóm cổ phiếu vốn hóa nhỏ, thanh khoản kém ở HNX/UPCOM. Trên nhóm cổ phiếu lớn thanh khoản cao ở HOSE, hiệu ứng này rất mỏng và dễ bị nuốt chửng bởi chi phí giao dịch.
- **Khuyến nghị:** Buộc thuật toán phải lọc thanh khoản khắt khe, không được ảo tưởng về quy mô quản lý tài sản hàng ngàn tỷ đồng chỉ dựa trên tín hiệu tin tức đơn thuần.

### 6.4. F203: Ma Trận Kiểm Toán Chế Độ 2D & Rào Cản Đóng Cứng (Fail-Closed Circuit Breaker)
- **Vai trò:** Lập ma trận kiểm toán 2 chiều (16 Giai đoạn thị trường lịch sử $\times$ 3 Sàn giao dịch), xác định các điều kiện biên nơi chiến lược bị phá vỡ.
- **Ưu điểm (Pros):**
  1. *Khám phá hiện tượng đảo dấu có hệ thống (Systemic Sign-Flips):* Chứng minh rằng trong 29/60 ô trạng thái (48.3%), giả thuyết bắt đáy bị đảo dấu âm thảm khốc: Khủng hoảng tài chính 2007 ($-3.30\%$), Khủng hoảng trái phiếu và bắt bớ 2022 ($-4.66\%$), Giai đoạn thắt chặt định lượng 2026 ($-3.26\%$).
  2. *Thiết lập Rào cản rủi ro đóng cứng (Fail-Closed Circuit Breaker):* Ban hành quy tắc cấm kỵ: Tuyệt đối không giải ngân mua bắt đáy khi VN-Index nằm dưới đường trung bình MA200 hoặc khi chỉ số rủi ro $VIX > 25$.
- **Nhược điểm (Cons):**
  1. *Làm giảm tần suất giao dịch của hệ thống:* Trong những năm thị trường suy thoái kéo dài (như năm 2022), hệ thống sẽ hoàn toàn đứng ngoài thị trường, không phát sinh bất kỳ giao dịch nào.
- **Khuyến nghị:** Đây là nhược điểm mang tính bảo vệ vốn sống còn; phải kiên quyết duy trì rào cản này trong mọi trường hợp.

---

## 7. Phân Tầng 5: Quy Trình NLP Đa Phương Thức & Nhất Quán Toán Học (Tier F3xx)

### 7.1. F301: Tinh Chỉnh PhoBERT-base Căn Chỉnh Thị Hiếu Thị Trường (FinDPO)
- **Vai trò:** Tinh chỉnh mô hình ngôn ngữ tiếng Việt PhoBERT-base với hàm mất mát căn chỉnh thị hiếu FinDPO (Direct Preference Optimization trong tài chính).
- **Ưu điểm (Pros):**
  1. *Tách rời ngữ pháp khỏi kỳ vọng giá (Decoupling Polarity):* Một bài báo có tiêu đề mang từ ngữ bi quan (ví dụ: "Doanh nghiệp báo lỗ kỷ lục") nhưng giá cổ phiếu đã phản ánh hết và tăng trở lại sẽ được mô hình FinDPO căn chỉnh nhãn ưu tiên theo đúng diễn biến giá thực tế.
  2. *Tối ưu hóa phần cứng hoàn hảo:* Huấn luyện thành công trên card đồ họa phổ thông NVIDIA GeForce RTX 3060 Laptop (6GB VRAM) với mức chiếm dụng tối đa chỉ **4.96 GB VRAM** (< 5.2 GB ngân sách cho phép), không bao giờ bị tràn bộ nhớ (Zero OOM).
  3. *Tích hợp checkpoint tự phục hồi:* Module `training_checkpoint.py` cho phép dừng và tiếp tục huấn luyện nguyên tử mà không mất dữ liệu.
- **Nhược điểm (Cons):**
  1. *Hiện tượng học thuộc nhãn từ điển (Distillation Overfitting):* Chỉ số F1 Macro đạt 99.89% thực chất phản ánh việc mô hình đã chưng cất hoàn hảo các nhãn sinh ra từ từ điển ban đầu; 91% nhãn trung tính làm giảm độ nhạy với các tin tức phân cực yếu.
- **Khuyến nghị:** Bổ sung dữ liệu dán nhãn thủ công từ các chuyên gia phân tích tài chính để tinh chỉnh đầu phân loại sắc thái sâu hơn.

### 7.2. F302: Mạng Nơ-ron Hợp Nhất Đa Phương Thức Cross-Attention
- **Vai trò:** Hợp nhất vector ngữ nghĩa văn bản của PhoBERT (768 chiều) với 24 chỉ số tài chính kế toán RankGauss (128 chiều) và bối cảnh vĩ mô Gray Code (128 chiều).
- **Ưu điểm (Pros):**
  1. *Giải quyết triệt để bệnh "Mù ngữ cảnh" (Context-Blindness):* Cùng một tin tức tiêu cực, nếu doanh nghiệp có cơ bản cực tốt (ROE > 25%, tiền mặt dồi dào, nợ vay thấp) thì tác động giá sẽ khác hoàn toàn với một doanh nghiệp đang bên bờ vực phá sản.
  2. *Cơ chế chú ý chéo đa đầu (Multi-Head Cross-Attention, 4 heads):* Cho phép văn bản tin tức tự động "hỏi" và truy xuất các thông tin tài chính tương ứng để tạo ra vector Alpha hợp nhất 128 chiều.
  3. *Độ chính xác dự báo hướng tăng:* Đạt độ chính xác dự báo hướng giá $T+5$ lên tới **46.07%**, vượt trội rõ rệt so với mức ngẫu nhiên 33.3% trong bài toán 3 lớp.
- **Nhược điểm (Cons):**
  1. *Số lượng tham số mô hình tăng lên:* Tầng hợp nhất bổ sung thêm 789,507 tham số cần được tối ưu hóa.
  2. *Độ phức tạp khi giải thích mô hình (Black-Box Explainability):* Khó khăn hơn trong việc giải thích cho nhà đầu tư biết trọng số ra quyết định đang nghiêng về tin tức hay do chỉ số tài chính.
- **Khuyến nghị:** Áp dụng kỹ thuật trích xuất trọng số chú ý (Attention Weight Visualizer) để xuất báo cáo giải thích nguyên nhân ra quyết định cho từng phiên.

### 7.3. F303: Tái Kiểm Định Đột Phá Alpha Đa Phương Thức
- **Vai trò:** Đưa điểm số của mô hình học sâu đa phương thức F302 vào kiểm định lại chiến lược hồi quy trung bình để chứng minh sự vượt trội so với baseline F201.
- **Ưu điểm (Pros):**
  1. *Quy mô tác động Alpha bùng nổ:*
     - Điểm Alpha đa phương thức giúp tăng Cohen's $d$ từ $0.0557$ lên **$0.0840$ (+50.8% so với baseline)** với $t = 11.55, p = 9.66 \times 10^{-31}$.
     - Ở các ngưỡng tin cậy cao (Continuous Alpha $S < 35$), Cohen's $d$ vọt lên tới **$0.1736$ (gấp 3.12 lần baseline)** với $t = 18.00, p = 2.18 \times 10^{-71}$.
  2. *Bằng chứng vững chắc chứng minh giá trị của AI:* Đập tan hoài nghi về việc áp dụng mô hình học sâu phức tạp chỉ gây lãng phí tài nguyên; chứng minh sự kết hợp giữa ngôn ngữ và định lượng thực sự tạo ra Alpha vượt trội.
- **Nhược điểm (Cons):**
  1. *Số lượng cơ hội giao dịch giảm đi:* Khi thắt chặt ngưỡng tin cậy từ $S < 45$ xuống $S < 35$, số lượng sự kiện đạt chuẩn giảm đi đáng kể, đồng nghĩa với việc dòng tiền phải chờ đợi lâu hơn.
- **Khuyến nghị:** Thiết lập cơ chế phân bổ tỷ trọng động: Giải ngân tỷ trọng nhỏ ở ngưỡng $S < 45$ và giải ngân tối đa ở ngưỡng $S < 35$.

### 7.4. F304: Cổng Giải Mã Ràng Buộc Tiên Đề Xác Suất Kolmogorov (HybridACD & V-FAN)
- **Vai trò:** Ứng dụng đột phá từ đề tài nghiên cứu HybridACD, biến đổi từ cơ chế can thiệp logit-bias chậm chạp trên LLM sinh văn bản sang cơ chế chiếu hình học đơn thể xác suất (Simplex-TCD) dạng giải tích siêu tốc trên mạng phân loại cảm xúc.
- **Ưu điểm (Pros):**
  1. *Bảo chứng toán học tuyệt đối (Kolmogorov Invariant):* Đảm bảo xác suất dự báo tuân thủ 100% các tiên đề xác suất Kolmogorov: $p^*_{\text{pos}} = q^*_{\text{neg}}$ với sai số toán học bằng $0.00e+00$ và tổng xác suất $\sum p^* = 1.0$ ở độ chính xác máy tính $2.22 \times 10^{-16}$.
  2. *Bộ sinh đối kháng V-FAN siêu tốc (Vietnamese Financial Fast Adversarial Negator):* Đạt tốc độ xử lý kỷ lục **0.0197 ms / bài báo**, nhanh hơn 25 lần so với ngân sách cho phép (< 0.50 ms), không phụ thuộc vào bất kỳ API LLM thương mại đắt đỏ nào.
  3. *Cải thiện sai số hiệu chuẩn Brier Score tới +29.51%:* Giảm sai số Brier từ $0.0439$ xuống **$0.0310$**, triệt tiêu hiện tượng mô hình tự tin thái quá vào các nhận định sai lầm.
  4. *Bộ lọc ảo giác & tin đồn truyền thông:* Loại bỏ thành công **4,715 bài báo nhiễu/giật gân (chiếm 9.7% tổng mẫu)** có mức độ vi phạm nhất quán logic cao ($V > 0.35$), nâng Cohen's $d$ sau cùng lên **$0.0852$**.
- **Nhược điểm (Cons):**
  1. *Hiện mới chỉ áp dụng quy tắc phủ định (NegChecker):* Khung lý thuyết 10 Checkers toàn diện của HybridACD (như And, Or, But, Consequence, Conditional) mới chỉ được triển khai đầy đủ trên Negation, các Checkers logic quan hệ liên câu còn lại đang ở dạng thiết kế mô phỏng.
- **Khuyến nghị:** Mở rộng V-FAN để hỗ trợ thêm Paraphrase Checker (diễn đạt lại) và Consequence Checker (hệ quả kéo theo) trong giai đoạn tới.

---

## 8. Phân Tầng 6: Quy Trình Triển Khai Thực Tế, Giám Sát & Thích Ứng (Tier F4xx)

### 8.1. F401: Dịch Vụ Suy Luận Trực Tuyến FastAPI Siêu Tốc (< 50ms)
- **Vai trò:** Cung cấp REST API microservice phục vụ việc chấm điểm tin tức và xuất khuyến nghị hành động theo thời gian thực (Real-time Streaming Inference).
- **Ưu điểm (Pros):**
  1. *Tốc độ phản hồi cực nhanh:* Benchmark 50 lần liên tiếp trên GPU RTX 3060 đạt:
     - Độ trễ trung bình: **8.99 ms**
     - Phân vị P50: **7.62 ms**
     - Phân vị P95: **20.11 ms**
     - Cực đại: **31.01 ms** (vượt xa yêu cầu khắt khe SLA < 50.0 ms).
  2. *Tối ưu hóa bó tiến trình song song (Batched Forward Pass):* Gộp cả bài báo gốc và câu đối kháng V-FAN vào một tensor batch duy nhất để đưa qua PhoBERT, giảm 50% thời gian xử lý GPU.
  3. *Bộ lọc trùng lặp SimHash 64-bit trong 0.1 ms:* Nhận diện ngay bài báo copy/syndicated trong bộ đệm trượt 6 giờ, trả về ngay hành động `IGNORE_NOISE` mà không tốn công chạy mô hình sâu.
  4. *Định danh cổ đông lớn và yếu nhân:* Tự động ánh xạ tên các chủ tịch, tổng giám đốc (Trần Hùng Huy $\to$ ACB, Bầu Đức $\to$ HAG, Hồ Hùng Anh $\to$ TCB) vào đúng mã chứng khoán.
  5. *Hệ số tin cậy nguồn tin ($W_{\text{source}}$):* Chiết khấu mạnh các tin đồn trên mạng xã hội ($W = 0.35$), ưu tiên tuyệt đối công văn UBCKNN ($W = 1.0$) và báo chí chính thống ($W = 0.85$).
- **Nhược điểm (Cons):**
  1. *Giới hạn bộ đệm SimHash trong RAM:* Bộ đệm lưu trữ SimHash 6 giờ được giữ trong RAM máy chủ; nếu khởi động lại dịch vụ mà không lưu cache ra đĩa thì lịch sử dedup ngắn hạn sẽ bị mất.
- **Khuyến nghị:** Đồng bộ hóa cache SimHash vào Redis hoặc DuckDB in-memory table có cơ chế lưu trữ định kỳ.

### 8.2. F402: Nhật Ký Đối Soát Lợi Nhuận Thực Tế & Giám Sát Trôi Dạt (Drift Monitor)
- **Vai trò:** Tự động ghi vết mọi dự báo của F401 và định kỳ đối soát với giá thực tế sau giờ giao dịch (15:30) để phát hiện hiện tượng suy thoái mô hình (Model Drift).
- **Ưu điểm (Pros):**
  1. *Ghi vết phi khóa (Non-blocking Telemetry):* Lưu trữ đầy đủ trạng thái toán học (vector xác suất $p^*$, điểm vi phạm $V$, trọng số $W_{\text{source}}$) vào bảng `meta.prediction_feedback_log` mà không làm chậm API streaming.
  2. *Đối soát chuẩn xác theo phiên giao dịch:* Khớp nối giá $T+1, T+5, T+30$ theo đúng chuỗi phiên làm việc của thị trường, hỗ trợ hoàn hảo trạng thái đối soát từng phần (Partial Reconciliation).
  3. *Rào chắn an toàn suy thoái tự động (Degradation Circuit Breaker):* Liên tục đo lường độ chính xác phân loại trượt (Rolling Directional Accuracy) và hệ số tương quan hạng Spearman (Rank-IC); lập tức kích hoạt cờ báo động ngắt mạch `SYSTEM_DEGRADED_HALT` nếu độ chính xác giảm xuống dưới **35%** hoặc Brier score vọt lên trên **0.060**.
- **Nhược điểm (Cons):**
  1. *Độ trễ phản hồi của dữ liệu nhãn thực tế:* Để có nhãn $T+30$, hệ thống bắt buộc phải chờ 30 phiên giao dịch (khoảng 1.5 tháng thực tế), do đó hiện tượng trôi dạt dài hạn không thể phát hiện ngay trong ngày đầu tiên.
- **Khuyến nghị:** Dùng nhãn $T+1$ và $T+5$ làm chỉ báo sớm (Early-Warning Indicator) cho hiện tượng trôi dạt ngắn hạn.

### 8.3. F403: Tự Động Tái Huấn Luyện Liên Tục PEFT Fusion Head (< 25s)
- **Vai trò:** Pipeline tự động thích ứng mô hình khi phát hiện trôi dạt hoặc khi đã tích lũy đủ $N \ge 2,000$ mẫu dữ liệu thực tế mới.
- **Ưu điểm (Pros):**
  1. *Bảo toàn tri thức, chống quên thảm họa (Parameter-Efficient PEFT):* Đóng băng hoàn toàn 100% xương sống ngôn ngữ PhoBERT-base (135 triệu tham số, `requires_grad=False`), triệt tiêu hoàn toàn hiện tượng quên thảm họa (Catastrophic Forgetting).
  2. *Thích ứng siêu tốc trên phần cứng cá nhân:* Chỉ tối ưu hóa 789,507 tham số của tầng Cross-Attention và các đầu ra (< 0.6% dung lượng mô hình); thời gian huấn luyện hội tụ 3 epoch chỉ mất **24.8 giây** trên GPU laptop RTX 3060 (vượt xa SLA 3 phút).
  3. *Cổng kiểm soát mô hình bóng (Shadow Model Gate):* Trọng số mới chỉ được thăng cấp lên môi trường production nếu độ chính xác trên tập kiểm tra độc lập vượt trội hơn mô hình hiện tại; nếu không đạt, mô hình ứng viên bị hủy bỏ và giữ nguyên mô hình cũ an toàn.
- **Nhược điểm (Cons):**
  1. *Cửa sổ trượt 6 tháng có thể bị quá khớp với sóng ngắn:* Nếu 6 tháng gần nhất là sóng tăng mạnh (Bull market), mô hình có thể thích nghi thái quá sang xu hướng mua và mất cảnh giác khi thị trường chuyển sang đi ngang.
- **Khuyến nghị:** Luôn trộn lẫn 20% dữ liệu từ các chu kỳ khủng hoảng lịch sử (Stress-test Replay Buffer) vào tập huấn luyện liên tục để giữ cho mô hình luôn có tính phòng thủ.

---

## 9. Phân Tầng 7: Quy Trình Đấu Trường Mô Phỏng Chiến Lược Monte Carlo (Tier F5xx)

### 9.1. F501: Đấu Trường Đa Bot & Bộ Mô Phỏng Vi Cấu Trúc Thị Trường Việt Nam
- **Vai trò:** Tổ chức giải đấu quyết định định lượng giữa 5 triết lý đầu tư (5 Bot Personas) trên 10,000 đường đi mô phỏng Monte Carlo qua 5 kịch bản thị trường điển hình của Việt Nam.
- **Ưu điểm (Pros):**
  1. *Mô phỏng chân thực vi cấu trúc thị trường Việt Nam:*
     - Khóa thanh toán $T+2.5$: Mua ngày $T$ thì ngày $T+1, T+2$ hoàn toàn không thể bán (`REJECTED_T25_LOCKED`), chỉ được bán từ đầu ngày $T+3$.
     - Biên độ trần sàn: Giới hạn biên độ biến động ngày $\pm 7\%$ (HOSE), $\pm 10\%$ (HNX), $\pm 15\%$ (UPCOM).
     - Thuế phí và trượt giá: Khấu trừ đầy đủ 0.15% phí mua, 0.25% phí bán + thuế TNCN, và 0.10% trượt giá lệnh.
  2. *Tái lấy mẫu bảo toàn tự tương quan (Stationary Block Bootstrap):* Áp dụng thuật toán Politis & Romano (1994) với độ dài khối trung bình 5 phiên, bảo tồn nguyên vẹn hiện tượng chum biến động (Volatility Clustering) và đuôi dày của thị trường tài chính.
  3. *Kết quả kiểm chứng vượt trội của HybridACD Sniper Bot:*
     - Trong bão tin đồn mạng xã hội: Giữ mức sụt giảm tài sản tối đa **MaxDD = 0.00%** và không thua lỗ phiên nào nhờ bộ lọc $V \le 0.35$ và $W_{\text{source}}$, trong khi bot đu đỉnh (Momentum) sụt giảm tài sản tới **-26.64%**.
     - Trong cú sốc Thiên nga đen: Mang lại lợi nhuận **+11.19%** với Sharpe ratio đạt **0.31**, trong khi các bot thông thường đều thua lỗ nặng nề.
  4. *Đánh giá rủi ro đuôi chuẩn xác:* Đo lường rủi ro thông qua giá trị chịu rủi ro có điều kiện (CVaR 95%) và tính toán hệ số Deflated Sharpe Ratio cho $N=5$ chiến lược thi đấu.
- **Nhược điểm (Cons):**
  1. *Giả định thanh khoản vô hạn trong biên độ trần sàn:* Bộ mô phỏng giả định rằng miễn là giá không chạm sàn thì lệnh luôn được khớp toàn bộ; trên thực tế tại các phiên bán tháo trắng bảng bên mua, nhà đầu tư hoàn toàn mất thanh khoản và không thể thoát hàng dù đã đến ngày $T+3$.
- **Khuyến nghị:** Bổ sung mô hình suy giảm xác suất khớp lệnh (Fill Probability Model) dựa trên khối lượng giao dịch bình quân 20 phiên của từng mã.

---

## 10. Phân Tầng 8: Quy Trình Hành Lang Pháp Lý, Quản Trị Rủi Ro & Sandbox (Tier F9xx)

### 10.1. F901: Rào Cản Tuân Thủ Pháp Lý & Khóa Cứng Đặt Lệnh (Chỉ Thị UBCKNN 09/2023)
- **Vai trò:** Rào cản kiểm soát tuân thủ quy chế thị trường chứng khoán Việt Nam, ngăn chặn tuyệt đối việc phát sinh lỗi pháp lý trước khi luật cho phép.
- **Ưu điểm (Pros):**
  1. *Đạo đức nghiên cứu & Tuân thủ pháp luật tuyệt đối (Rule B1):* Tôn trọng nghiêm túc chỉ đạo của Ủy ban Chứng khoán Nhà nước (UBCKNN) tháng 09/2023 về việc tạm dừng dịch vụ đặt lệnh robot tự động tần suất lớn để bảo vệ sự ổn định của hệ thống giao dịch quốc gia.
  2. *Khóa cứng tầng thực thi (Hard Compliance Lock):* Trạng thái F901 được giữ nguyên là `blocked`; toàn bộ mã nguồn VESTA hiện tại được cô lập thành hệ thống **100% CHỈ ĐỌC (Strictly Read-Only)**, không tồn tại bất kỳ dòng lệnh nào có khả năng tự ý kết nối API tài khoản tiền thật.
  3. *Bảo vệ an toàn tuyệt đối tài sản:* Tránh được mọi rủi ro về lỗi phần mềm dẫn đến việc đặt lệnh mất kiểm soát làm cháy tài khoản hoặc vi phạm quy chế giao dịch của Sở.
- **Nhược điểm (Cons):**
  1. *Hạn chế việc tự động hóa toàn diện:* Nhà đầu tư vẫn phải thực hiện thao tác đặt lệnh thủ công bằng tay dựa trên tín hiệu khuyến nghị của hệ thống.
- **Khuyến nghị:** Tiếp tục theo dõi lộ trình ban hành Thông tư hướng dẫn giao dịch thuật toán mới của Bộ Tài chính và UBCKNN sau khi hệ thống công nghệ KRX vận hành ổn định.

### 10.2. F902: Hạ Tầng Định Tuyến Lệnh Giả Lập Sandbox (SSI / DNSE Paper Trading)
- **Vai trò:** Thiết kế module trung gian sẵn sàng kết nối vào cổng thử nghiệm (Paper Trading Sandbox) của các CTCK có API mở (như DNSE Open API hoặc SSI FastConnect) bằng cơ chế xác thực OAuth2 + PKCE.
- **Ưu điểm (Pros):**
  1. *Sẵn sàng kích hoạt không trễ (Zero-Friction Readiness):* Toàn bộ kiến trúc dữ liệu và logic sinh lệnh đã được đóng gói chuẩn mực; khi hành lang pháp lý F901 được thông qua, hệ thống chỉ mất 1 ngày để kích hoạt kết nối sandbox.
  2. *Kiểm thử trượt giá không rủi ro vốn:* Cho phép đo lường chính xác độ trễ mạng Internet và mức độ trượt giá thực tế giữa thời điểm sinh tín hiệu và thời điểm lệnh vào sổ của sở.
- **Nhược điểm (Cons):**
  1. *Hiện đang bị khóa phụ thuộc hoàn toàn vào F901:* Không được phép triển khai code thực tế cho đến khi rào cản pháp lý F901 được xác nhận bằng văn bản chính thức.
- **Khuyến nghị:** Giữ nguyên trạng thái stub mô phỏng trong môi trường test pipeline (`test_pipeline/`).

---

## 11. Các Quy Trình Kiến Trúc & Vận Hành Bổ Trợ Đặc Thù

### 11.1. Concurrency Gate: Xử Lý Khóa Tệp CSDL DuckDB Trên Hệ Điều Hành Windows
- **Bản chất vấn đề:** DuckDB trên Windows sử dụng Windows API locking cơ chế độc quyền. Khi một tiến trình đang mở tệp `vesta.duckdb` ở chế độ ghi, bất kỳ tiến trình nào khác (như FastAPI service hoặc kiểm thử pytest) cố gắng đọc/ghi đều sẽ bị ném lỗi khóa tệp ngay lập tức.
- **Ưu điểm giải pháp của VESTA:**
  - Áp dụng mô hình CSDL phân tách: Các tiến trình cào dữ liệu ghi vào `vesta_staging.duckdb`.
  - Tiến trình chính chỉ mở giao dịch nguyên tử chớp nhoáng (Atomic Transaction) để copy dữ liệu vào `vesta.duckdb` rồi đóng kết nối ngay lập tức.
  - Dịch vụ FastAPI mở kết nối ở chế độ chỉ đọc chuyên biệt (`read_only=True`), cho phép nhiều luồng đọc đồng thời mà không xung đột.
- **Nhược điểm:** Đòi hỏi lập trình viên phải luôn nhớ sử dụng context manager (`with get_db_connection() as conn:`) và không được giữ kết nối mở lâu.

### 11.2. Loop Engineering & CI/CD Regression Invariant Testing Suite
- **Ưu điểm:**
  - Bộ kiểm thử tự động toàn diện gồm hơn **339 test cases** phủ kín mọi module từ F000 đến F501.
  - Nguyên tắc kiểm tra tính bất biến (Invariant Tests): Đảm bảo các đặc tính toán học cốt lõi (như Kolmogorov simplex $\sum p^* = 1$, giá $Low \le High$, $T+2.5$ settlement lock) không bao giờ bị phá vỡ qua các phiên bản code.
- **Nhược điểm:** Thời gian chạy toàn bộ test suite có thể mất từ 3 đến 5 phút nếu chạy tuần tự.
- **Khuyến nghị:** Sử dụng `pytest -n auto` để chạy kiểm thử song song đa lõi CPU.

### 11.3. Entity Resolution: Phân Giải Thực Thể Lãnh Đạo & Cổ Đông Lớn
- **Ưu điểm:**
  - Module `shareholder_entity_matcher.py` kết nối trực tiếp với 4,268 bản ghi cổ đông và lãnh đạo doanh nghiệp trong CSDL.
  - Tự động nhận diện các biệt danh thương trường phổ biến ở Việt Nam (ví dụ: "Bầu Đức" $\to$ Đoàn Nguyên Đức $\to$ HAG, "Vua thép" $\to$ Trần Đình Long $\to$ HPG).
- **Nhược điểm:** Chưa bao phủ hết các mối quan hệ sở hữu chéo phức tạp (Cross-Ownership) giữa các công ty con, công ty liên kết chưa niêm yết.
- **Khuyến nghị:** Xây dựng đồ thị tri thức mạng lưới sở hữu (Knowledge Graph of Corporate Ownership) bằng thư viện NetworkX để dò vết dòng tiền sở hữu gián tiếp.

---

## 12. Bảng So Sánh Trade-offs Giữa Các Giải Pháp Kỹ Thuật Đã Chọn

| Vấn Đề Kỹ Thuật | Phương Pháp Truyền Thống / Lựa Chọn Bị Bác Bỏ | Phương Pháp Đột Phá Được Chọn Của VESTA | Lý Do & Đánh Đổi Kỹ Thuật (Trade-off Rationale) |
| :--- | :--- | :--- | :--- |
| **Hạ tầng CSDL Phân tích** | PostgreSQL / MySQL | **DuckDB Columnar In-Process OLAP** | **Đánh đổi:** Chấp nhận hạn chế khóa file trên Windows để đổi lấy tốc độ truy vấn hình cột nhanh gấp 30 lần trên tập dữ liệu hàng triệu nến mà không cần cài đặt máy chủ CSDL cồng kềnh. |
| **Tính Nhất Quán Xác Suất** | Chạy LLM sinh chuỗi kèm Logit-Bias (HybridACD gốc) | **Simplex-TCD Orthogonal Projection (Giải tích)** | **Đánh đổi:** Không sinh được giải thích văn bản tự do, nhưng giảm độ trễ từ hàng ngàn mili-giây xuống **0.0197 ms**, bảo đảm tiên đề Kolmogorov chính xác $0.00e+00$ và đáp ứng chuẩn thời gian thực. |
| **Căn Chỉnh Mô Hình Ngôn Ngữ** | Huấn luyện phân loại Cross-Entropy thông thường | **FinDPO Direct Preference Optimization** | **Đánh đổi:** Đòi hỏi dữ liệu đối soát lợi nhuận thực tế phức tạp hơn, nhưng giải quyết được hiện tượng nghịch lý: tin tiêu cực ngữ pháp nhưng giá tăng lại được mô hình nhận diện chuẩn xác. |
| **Bộ Ngữ Liệu Văn Bản Tin Tức** | Chỉ cào tiêu đề ngắn từ RSS | **Bóc tách toàn văn HTML (1,500 - 8,000 ký tự)** | **Đánh đổi:** Tốn dung lượng đĩa và thời gian cào chậm hơn do độ trễ lịch sự 1.0s, nhưng giúp mô hình nắm bắt đầy đủ bối cảnh phân tích sâu và trích xuất đúng thực thể doanh nghiệp. |
| **Xử Lý Chuỗi Giá Chuẩn Hóa** | Lấy sai phân bậc 1 ($d=1$) làm mất trí nhớ lịch sử | **Fractional Differentiation (FFD $d=0.20$)** | **Đánh đổi:** Tốn chi phí tính toán cửa sổ trượt quá khứ, nhưng giữ lại được hơn 80% bộ nhớ dài hạn của chuỗi giá gốc trong khi vẫn đạt tính dừng thống kê ($p < 0.01$). |
| **Quy Chuẩn Ra Quyết Định** | Bắt đáy tin xấu vô điều kiện dựa trên Student-t test | **Rào cản đóng cứng theo chế độ (Fail-Closed Gate)** | **Đánh đổi:** Bỏ lỡ cơ hội giao dịch trong các năm thị trường suy thoái, nhưng bảo vệ hệ thống không bị phá sản trong các cuộc khủng hoảng thanh khoản hệ thống (2008, 2022). |
| **Thực Thi Lệnh Giao Dịch** | Cố gắng viết bot lách luật đặt lệnh tự động | **Khóa cứng tuân thủ 100% (Strictly Read-Only)** | **Đánh đổi:** Chưa thể giao dịch tự động hoàn toàn, nhưng bảo đảm tuyệt đối tính pháp lý, tuân thủ chỉ thị UBCKNN và an toàn vốn của người sử dụng. |

---

## 13. Đề Xuất Lộ Trình Tối Ưu Hóa & Khắc Phục Nhược Điểm (Actionable Roadmap)

Dựa trên toàn bộ các nhược điểm (Cons) và rủi ro kỹ thuật đã được bóc tách tỉ mỉ ở các phần trên, dưới đây là **4 nhóm hành động ưu tiên cao nhất** cho các chu kỳ phát triển tiếp theo của VESTA:

### Nhóm 1: Tối Ưu Hóa Tầng Dữ Liệu & Khắc Phục Lỗ Hổng BCTC (Data Layer Remediation)
1. **Tháo gỡ điểm nghẽn F052 (CafeF BCTC Gap-Fix):** Hoàn thiện module chuyển đổi chuẩn mã tài khoản giữa CafeF và vnstock, chính thức đưa Bảng cân đối kế toán lịch sử vào bảng `core.fundamentals` thay vì dựa vào quyết định chấp nhận thiếu hụt.
2. **Loại bỏ nến rác không thanh khoản (Liquidity Filtering):** Đóng cứng bộ lọc giá trị giao dịch tối thiểu (ví dụ: bình quân 20 phiên $> 1$ tỷ VNĐ/phiên) ngay tại tầng F102 để loại bỏ hoàn toàn các mã penny bị đóng băng làm méo mó thống kê.
3. **Thu thập ngày công bố BCTC thực tế:** Kết nối cổng công bố thông tin chính thức của HOSE/HNX để thay thế cho mốc ước lượng pháp lý 30 ngày.

### Nhóm 2: Nâng Cấp Năng Lực Mô Hình Ngôn Ngữ & Mở Rộng 10 Checkers (AI & NLP Evolution)
1. **Tích hợp SLM thế hệ mới (Qwen2.5-3B-Instruct 4-bit):** Hiện thực hóa lộ trình đưa mô hình ngôn ngữ nhỏ lượng tử hóa 4-bit (~2.2 GB VRAM) vào làm bộ não phân tích sâu bên cạnh PhoBERT, khai thác năng lực suy luận logic phức tạp trên card đồ họa RTX 3060.
2. **Hiện thực hóa trọn vẹn Khung 10 Checkers Kolmogorov:** Mở rộng từ Negation sang các phép toán logic liên câu: `AndOrChecker`, `ConditionalChecker`, `ExpectedEvidenceChecker` theo thiết kế trong `src/pipeline/f3xx_modeling/hybridacd_multi_checkers.py`.
3. **Mạng đồ thị tri thức doanh nghiệp (Enterprise Knowledge Graph):** Xây dựng đồ thị liên kết giữa các tập đoàn mẹ - con và mạng lưới cổ đông lớn để lan truyền tín hiệu cảm xúc xuyên chuỗi giá trị.

### Nhóm 3: Nâng Cấp Bộ Mô Phỏng Vi Cấu Trúc Thực Tế (Execution & Microstructure Refinement)
1. **Mô hình hóa rủi ro mất thanh khoản sàn (Zero-Bid Floor Liquidity Model):** Đưa xác suất không thể khớp lệnh bán khi cổ phiếu giảm sàn dư bán hàng triệu đơn vị vào bộ mô phỏng Monte Carlo F501.
2. **Chiết khấu dòng tiền ngoại đột biến:** Bóc tách các lệnh thỏa thuận nghìn tỷ của khối ngoại ra khỏi chuỗi dữ liệu khớp lệnh liên tục của F051.

### Nhóm 4: Chuẩn Bị Pháp Lý & Thử Nghiệm Sandbox An Toàn (Regulatory & Sandbox Readiness)
1. **Hoàn thiện bộ kết nối DNSE / SSI Sandbox:** Xây dựng đầy đủ lớp xác thực OAuth2 + PKCE và cơ chế quản lý token bảo mật trong `src/execution/` dưới chế độ cách ly hoàn toàn với môi trường tiền thật.
2. **Vận hành hệ thống dưới dạng Trợ lý Tư vấn Bán Tự Động (Human-in-the-Loop Co-Pilot):** Trong khi chờ đợi hành lang pháp lý mở cửa cho bot tự động hoàn toàn, hệ thống F401 sẽ đóng vai trò xuất tín hiệu cảnh báo sớm và đề xuất danh mục lên màn hình GUI cho nhà đầu tư tự bấm xác nhận đặt lệnh trên app chứng khoán chính thống.

---

### KẾT LUẬN NGHIỆM THU

Báo cáo trên đã hoàn thành trọn vẹn yêu cầu kiểm toán và tổng hợp chi tiết ưu điểm, nhược điểm của **tất cả 37 quy trình kỹ thuật trọng yếu** trong toàn bộ hệ thống VESTA. Bằng việc nhìn thẳng vào các hạn chế cốt tử (Cons) song hành cùng các đột phá khoa học (Pros), đội ngũ phát triển đã xác lập một nền tảng định lượng trung thực, an toàn và sẵn sàng cho các bước tiến thực chiến tiếp theo.

---
*Báo cáo được biên soạn và lưu trữ tại `d:\VESTA\Progress Report\08_COMPREHENSIVE_PROS_AND_CONS_ALL_PROCESSES_REPORT.md`.*
