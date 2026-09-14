# ĐỀ CƯƠNG NGHIÊN CỨU

## Thiết Kế Mô Hình Tác Nhân Tự Quyết Định Giao Dịch Trong Thị Trường Chứng Khoán Việt Nam Dựa Vào Tín Hiệu Cảm Xúc Có Kiểm Chứng Độ Nhất Quán Thông Qua Các Mô Hình Ngôn Ngữ

**English title:** Designing an Autonomous Decision-Making Agent for Trading in the Vietnamese Stock Market Based on Consistency-Verified Sentiment Signals via Language Models

---

# CHƯƠNG 1 — TỔNG QUAN ĐỀ TÀI

## 1.1 Tính cấp thiết và bối cảnh nghiên cứu

Thị trường chứng khoán Việt Nam có đặc điểm cấu trúc khác biệt rõ rệt so với các thị trường phát triển: hơn 90% giá trị giao dịch hàng ngày đến từ nhà đầu tư cá nhân, với khoảng 11,9 triệu tài khoản chứng khoán tính đến cuối năm 2025 (nguồn: thevietnamyield.com, 2/2026) — tỷ lệ nhà đầu tư cá nhân cao bất thường này tạo tiền đề hợp lý cho giả thuyết rằng thị trường dễ bị chi phối bởi tâm lý đám đông và phản ứng thái quá trước tin tức hơn là bởi phân tích cơ bản thuần túy.

Đồng thời, hạ tầng giao dịch của thị trường vừa trải qua một thay đổi lớn: hệ thống công nghệ mới (KRX) chính thức đi vào vận hành từ tháng 5 năm 2025 (nguồn: theinvestor.vn, vietnamnet.vn, vietnamnews.vn), thay đổi một số cơ chế khớp lệnh quan trọng (lệnh ATO/ATC không còn ưu tiên tuyệt đối, bổ sung T+0, bán khống, CCP) — đây là một điểm mốc cấu trúc thị trường cần được ghi nhận khi xử lý dữ liệu trải dài qua nhiều năm.

Về mặt pháp lý, cơ quan quản lý thị trường đã có động thái hạn chế rõ ràng đối với hình thức đặt lệnh tự động tần suất lớn từ tháng 9/2023 (xác nhận qua công văn UBCKNN, người phát ngôn: ông Hoàng Văn Thu, Phó Chủ tịch UBCKNN, được tường thuật bởi VnEconomy, Tuổi Trẻ, Thanh Niên, PLO, VOV) do lo ngại về khả năng chịu tải của hệ thống giao dịch — đây là lý do chính đáng và có căn cứ thực tế để đề tài giới hạn phạm vi ở việc chứng minh tín hiệu giao dịch, không mở rộng sang xây dựng hệ thống đặt lệnh tự động thật.

Về mặt học thuật, các nghiên cứu ứng dụng trí tuệ nhân tạo cho thị trường chứng khoán Việt Nam đã đạt một số kết quả đáng chú ý — từ phương pháp học máy truyền thống (SVM + TF-IDF, độ chính xác dự đoán hướng chỉ số khoảng 60%) đến các mô hình ngôn ngữ chuyên biệt tiếng Việt (PhoBERT) đạt độ chính xác phân loại cảm xúc tin tức tài chính từ 81% đến hơn 93% (Preprints.org 2023; NEU-Stock/CEUR-WS 2021; github.com/209sontung). Tuy nhiên, khảo sát trực tiếp các nghiên cứu gốc cho thấy một khoảng trống quan trọng: **phần lớn các nghiên cứu này dừng lại ở việc chứng minh mô hình phân loại cảm xúc chính xác, mà chưa kiểm định nghiêm ngặt xem tín hiệu cảm xúc đó có thực sự chuyển hóa thành một cơ hội giao dịch có ý nghĩa thống kê vững chắc hay không**. Cụ thể, một nghiên cứu (Preprints.org, 2023) cho thấy dù mô hình phân loại cảm xúc đạt độ chính xác >81%, phản ứng giá trước và sau khi tin được công bố lại không có sự khác biệt có ý nghĩa thống kê. Đây chính là khoảng trống mà đề tài hướng đến lấp đầy.

## 1.2 Đối tượng nghiên cứu

**Đối tượng chính:** mối quan hệ nhân quả có thể khai thác được giữa sắc thái cảm xúc của tin tức tài chính tiếng Việt và diễn biến giá cổ phiếu sau đó trên thị trường chứng khoán Việt Nam — cụ thể là hiện tượng phản ứng thái quá ngắn hạn rồi đảo chiều (mean-reversion sau sentiment shock). Đây không phải nghiên cứu dự đoán giá cổ phiếu nói chung, mà tập trung hẹp vào một cơ chế hành vi cụ thể.

**Đơn vị phân tích (unit of analysis):** mỗi "sự kiện tin tức" — cặp (mã cổ phiếu, bài báo tài chính, thời điểm công bố) — được gắn với ba mốc giá tương lai chuẩn hóa (T+1, T+5, T+30 ngày giao dịch).

**Đối tượng khảo sát mở rộng:**
- *Doanh nghiệp niêm yết:* toàn bộ cổ phiếu đang giao dịch và đã hủy niêm yết trên ba sàn HOSE, HNX, UPCOM.
- *Văn bản tin tức tài chính tiếng Việt:* nhiều nguồn tin về doanh nghiệp niêm yết và bối cảnh vĩ mô.
- *Nhà đầu tư cá nhân:* **không được khảo sát trực tiếp** — là chủ thể hành vi được suy luận gián tiếp qua dấu vết để lại trên giá. Cần nêu rõ giới hạn này để tránh gây hiểu lầm là có bằng chứng hành vi học trực tiếp.
- *Mô hình ngôn ngữ nhỏ tiếng Việt (PhoBERT):* công cụ đo lường trung gian (measurement instrument) cho biến "cảm xúc tin tức", không phải đối tượng nghiên cứu cuối cùng.

**Phạm vi thời gian của đối tượng:** dữ liệu trải dài từ khoảng 2007 đến 2026, nhưng mật độ quan sát tăng mạnh từ 2019 trở đi (do đặc điểm tích lũy dữ liệu tin tức chỉ có thể tiến về phía trước từ thời điểm bắt đầu thu thập) — mẫu nghiên cứu không đồng nhất theo thời gian, cần nêu rõ khi diễn giải kết quả tổng hợp toàn kỳ.

**Ngoài phạm vi đối tượng nghiên cứu:** định giá tuyệt đối cổ phiếu; chiến lược giao dịch tần suất cao dựa trên độ sâu sổ lệnh; hành vi nhà đầu tư tổ chức/nước ngoài; phân tích rủi ro tín dụng/định giá cơ bản truyền thống.

## 1.3 Mục tiêu nghiên cứu

**Mục tiêu tổng quát:** Xây dựng và kiểm định một cách khoa học, minh bạch một hệ thống nhận diện tín hiệu giao dịch dựa trên cảm xúc thị trường trích xuất từ tin tức tài chính tiếng Việt, đạt tiêu chuẩn kiểm định thống kê tương đương hoặc cao hơn thông lệ quốc tế trong tài chính định lượng, làm nền tảng cho một tác nhân AI có khả năng tự quyết định hỗ trợ giao dịch trong tương lai.

**Mục tiêu cụ thể:**
1. Xây dựng quy trình thu thập và xử lý dữ liệu tài chính thị trường Việt Nam đảm bảo tuyệt đối tính đúng-thời-điểm (không có thông tin tương lai nào bị vô tình sử dụng để phân tích quá khứ).
2. Kiểm định nghiêm ngặt giả thuyết "đảo chiều tâm lý sau tin tức tiêu cực" bằng công cụ thống kê chuyên sâu: kiểm định vững theo cụm, tỷ số Sharpe khử lạm phát (Deflated Sharpe Ratio), xác suất quá khớp backtest (Probability of Backtest Overfitting), và kiểm tra ổn định theo giai đoạn thị trường lẫn phân khúc thanh khoản.
3. Nếu và chỉ nếu giả thuyết trên được chứng minh vững chắc, xây dựng một mô hình ngôn ngữ nhỏ tiếng Việt tinh chỉnh chuyên biệt để chấm điểm cảm xúc tài chính.
4. Đề xuất (và tùy thời gian, triển khai) một lớp kiểm chứng tính nhất quán xác suất giữa tầng mô hình ngôn ngữ và tầng ra quyết định.
5. Tuân thủ nghiêm ngặt nguyên tắc "chứng minh tín hiệu trước khi xây hạ tầng thực thi" — không xây dựng bất kỳ thành phần đặt lệnh giao dịch thật nào cho đến khi cả điều kiện khoa học và điều kiện pháp lý đều được đáp ứng.

## 1.4 Phạm vi nghiên cứu

| Thành phần | Trong phạm vi | Ngoài phạm vi (giai đoạn hiện tại) |
|---|---|---|
| Dữ liệu giá/tài chính | OHLCV, báo cáo tài chính, sự kiện doanh nghiệp — HOSE/HNX/UPCOM | Phái sinh, trái phiếu, tiền mã hóa |
| Tin tức | Tiếng Việt — nguồn về doanh nghiệp niêm yết và vĩ mô trong nước | — |
| Dữ liệu quốc tế | Có tồn tại trong kho (S&P 500, VIX, DXY, US 10Y, giá dầu, tỷ giá USD/VND, 2000-2026) nhưng **chưa được tích hợp vào pipeline phân tích tín hiệu** — dùng làm biến kiểm soát dự kiến ở giai đoạn audit regime | Mở rộng sentiment sang tin tức tiếng Anh |
| Mô hình ngôn ngữ | PhoBERT (SLM tiếng Việt, ~110M tham số, tinh chỉnh trên RTX 3060 6GB) | LLM lớn đa năng làm bộ chấm điểm chính |
| Thực thi giao dịch | Hoàn toàn ngoài phạm vi kỹ thuật, khóa cứng cho đến khi có xác nhận pháp lý | — |

**Lưu ý về khoảng trống phạm vi:** tên đề tài đầy đủ có thể gợi ý phạm vi quốc tế, nhưng phạm vi kỹ thuật đã triển khai hiện tập trung vào dữ liệu Việt Nam/tiếng Việt là chính; dữ liệu quốc tế đóng vai trò biến kiểm soát bối cảnh, không phải đối tượng phân tích trung tâm.

## 1.5 Ý nghĩa khoa học và thực tiễn

**Ý nghĩa khoa học:** đề tài lấp một khoảng trống phương pháp luận rõ ràng trong các nghiên cứu ứng dụng AI cho thị trường chứng khoán Việt Nam — áp dụng đầy đủ khung kiểm định thống kê chuẩn quốc tế (Deflated Sharpe Ratio, Probability of Backtest Overfitting theo López de Prado) thay vì chỉ dừng ở kiểm định thô dễ gây ảo giác ý nghĩa thống kê khi cỡ mẫu lớn — điều mà không nghiên cứu VN nào đã khảo sát áp dụng.

**Ý nghĩa thực tiễn:** kết quả nghiên cứu, dù theo chiều hướng nào (tín hiệu vững hay tín hiệu có điều kiện), đều cung cấp thông tin có giá trị cho nhà đầu tư và nhà nghiên cứu về đặc tính hành vi của thị trường chứng khoán Việt Nam, đặc biệt là mối quan hệ giữa quy mô hiệu ứng thống kê và khả năng khai thác thực tế (đã phát hiện sơ bộ "Nghịch lý khả thi giao dịch" — hiệu ứng mạnh nhất nằm ở nhóm cổ phiếu khó giao dịch nhất).

---

# CHƯƠNG 2 — TỔNG QUAN TÀI LIỆU VÀ SO SÁNH PHƯƠNG PHÁP

## 2.1 Khái quát công việc đã và đang thực hiện (không dùng ký hiệu mã hóa nội bộ)

Toàn bộ công việc được tổ chức thành sáu giai đoạn lớn, mỗi giai đoạn chỉ bắt đầu khi giai đoạn trước có bằng chứng thực nghiệm xác nhận:

1. **Thu thập dữ liệu nền tảng** — danh mục mã cổ phiếu, giá giao dịch, báo cáo tài chính, sự kiện doanh nghiệp, hai nguồn tin tức tài chính tiếng Việt độc lập. Đã hoàn tất, qua một vòng kiểm tra chéo phát hiện và sửa một số sai sót thực tế.
2. **Ghép nối dữ liệu đúng thời điểm** — đảm bảo mỗi sự kiện tin tức được gắn đúng mức giá tại các mốc thời gian sau đó mà không rò rỉ thông tin tương lai. Đã hoàn tất.
3. **Kiểm định giả thuyết tín hiệu** (giai đoạn trọng tâm) — kiểm định thống kê nghiêm ngặt trên hơn 15.000 sự kiện tin tức tiêu cực thực tế, bao gồm kiểm tra độ vững, khử outlier có căn cứ, và kiểm tra ổn định theo giai đoạn thị trường và phân khúc thanh khoản. Đã hoàn thành phần lõi, đang audit sâu hơn.
4. **Xây dựng mô hình học máy chấm điểm cảm xúc** — chỉ bắt đầu sau khi giai đoạn 3 chứng minh chắc chắn tín hiệu tồn tại vững. Chưa bắt đầu.
5. **Lớp kiểm chứng tính nhất quán logic** — điểm giao thoa với nghiên cứu song song (HybridACD), tạm hoãn theo quyết định của người thực hiện đề tài.
6. **Dịch vụ suy luận và giám sát** — chưa bắt đầu.

Tầng thực thi giao dịch thật nằm hoàn toàn ngoài phạm vi kỹ thuật hiện tại, khóa có chủ đích cho đến khi có xác nhận pháp lý chính thức.

## 2.2 Bảng so sánh chi tiết các công trình nghiên cứu đã tổng hợp

### 2.2.1 Nhóm A — Dự báo giá/sentiment cổ phiếu Việt Nam

| Tên nghiên cứu | Tác giả | Phương pháp/Mô hình | Kết quả | Ưu điểm | Nhược điểm |
|---|---|---|---|---|---|
| Dự đoán hướng VN-Index từ tin tức | Chưa xác định lại được nguồn cụ thể | SVM + TF-IDF trên ~70.000 bài báo | ~60% accuracy hướng đi *(chưa verify lại)* | Nỗ lực sớm kết hợp text mining với dự đoán chỉ số | TF-IDF không nắm ngữ nghĩa; không kiểm tra ý nghĩa thống kê |
| NEU-Stock | Tran et al. (2021), CEUR-WS Vol-3026 | PhoBERT (đếm bài theo lớp) + LSTM-Attention | R²=0,933; RMSE=730,754; MAPE=1,338 (đã đọc trực tiếp bảng gốc, xác nhận đúng) | R² cao; PhoBERT xử lý tốt tiếng Việt | Test chỉ 200 mẫu/1 mã; không CPCV; sentiment rời rạc thô; R² cao có thể do tự tương quan giá |
| Sentiments Extracted from News... | Preprints.org (2023) | PhoBERT fine-tune, ~40.000 bài, 3 lớp | Accuracy >81%; phản ứng giá KHÔNG có ý nghĩa thống kê | Minh bạch báo cáo cả kết quả "âm tính" | Không chứng minh được giá trị giao dịch thực tế |
| Vietnamese-stock-article-classification | github.com/209sontung | PhoBERT phân loại tiêu đề | ~93% accuracy, ~1.000 tiêu đề | Accuracy cao nhất nhóm | Không phải publication học thuật; không backtest giá |
| Investor sentiment and market returns | Nguyen et al. (2025), RIBAF, Elsevier | Phân tích đa khung thời gian | Sentiment dự báo tốt hơn AR thuần giá, mạnh ở đuôi lợi nhuận thấp | Có bình duyệt; đa khung thời gian | Chưa rõ có kiểm tra multiple-testing hay không |
| ML + DEA + auto feature engineering | PLOS ONE (9/2025) | DNN/GBT + điểm hiệu quả DEA | RMSE 0,926→0,375; GBT+DEA MAPE=103,19 (tốt nhất) | Có bình duyệt; so sánh nhiều mô hình | Giới hạn 1 ngành (BĐS, 26 DN) |

### 2.2.2 Nhóm B — Kỷ luật thống kê tài chính định lượng

| Tên nghiên cứu | Tác giả | Phương pháp | Kết quả | Ưu điểm | Nhược điểm |
|---|---|---|---|---|---|
| Deflated Sharpe Ratio | Bailey & López de Prado (2014) | Hiệu chỉnh Sharpe theo N trials và moment bậc cao | Framework toán học phân biệt alpha thật/data-snooping | Chuẩn mực ngành quant | Thiết kế cho Sharpe chuỗi thời gian; chuyển sang bối cảnh event-study là thích nghi cần biện minh |
| Probability of Backtest Overfitting | Bailey, Borwein, López de Prado, Zhu | CSCV — chia block, so sánh rank IS/OOS | PBO ví dụ gốc =13% | Không phụ thuộc giả định phân phối | Cần ≥2 biến thể để so sánh |
| Advances in Financial ML | López de Prado (2018) | Walk-Forward, purge/embargo | Chuẩn ngành chống rò rỉ qua biên train/test | Giải quyết tự tương quan chuỗi thời gian | Cần khối lượng dữ liệu lớn |
| Square-root impact law | Tóth et al., arXiv:1602.03043 | Mô hình slippage căn bậc hai | Xác nhận trên ~500.000 giao dịch phái sinh | Cơ sở thực nghiệm rộng | Đo trên thị trường quốc tế, chưa chắc khớp HOSE |

### 2.2.3 Nhóm C — LLM/SLM fine-tuning và Hybrid RAG

| Tên nghiên cứu | Tác giả | Phương pháp | Kết quả | Ưu điểm | Nhược điểm |
|---|---|---|---|---|---|
| FinDPO | arXiv:2507.18417, ACM ICAIF 2025 | DPO cho sentiment tài chính | +11% so SFT; S&P 500 2015-2021: +67%/năm, Sharpe 2,0 | Tránh vòng lặp RLHF; điểm liên tục | Benchmark hoàn toàn trên thị trường Mỹ |
| BM25 to Corrective RAG | arXiv:2604.01733 | Benchmark hybrid retrieval tài chính | BM25 vượt dense retrieval SOTA trên tài liệu tài chính | Đúng domain, cỡ mẫu lớn | Chưa có nhu cầu dùng trong VESTA hiện tại |

### 2.2.4 Nhóm D — Tính nhất quán xác suất mô hình ngôn ngữ

| Tên nghiên cứu | Tác giả | Phương pháp | Kết quả | Ưu điểm | Nhược điểm |
|---|---|---|---|---|---|
| Consistency Checks for LM Forecasters | Paleka et al. (2025), arXiv:2412.18544 (đọc toàn văn) | 10 quy tắc nhất quán; ArbitrageForecaster (hậu xử lý đại số) | Giảm vi phạm Negation ~89% nhưng Brier Score XẤU ĐI | Nền móng lý thuyết vững; minh bạch cả kết quả bất lợi | Tốn kém (~$2.500/câu hỏi); Goodhart's Law xảy ra thật |
| Token Constraint Decoding | Yao et al. (2025), arXiv:2506.09408 (xác minh tồn tại thật) | Giới hạn token hợp lệ khi decode (MCQA) | +39% cho mô hình yếu | Chi phí thấp | Thử nghiệm trên MCQA, không phải forecasting xác suất |
| HybridACD | Trần Anh Kiệt (2026, chưa bình duyệt), UIT-VNU HCM | Adversarial rewriting + TCD | AVS giảm 95,5% (0,1522→0,0053); Brier cải thiện 2,4-17,3% (đã tự tính lại, khớp chính xác) | Rẻ hơn ArbitrageForecaster hàng nghìn lần; không rơi Goodhart | Chưa bình duyệt độc lập; chưa có tiền lệ cho classification-head như PhoBERT |

### 2.2.5 Dòng đối chiếu — Phương pháp đang thực hiện (VESTA)

| Tên nghiên cứu | Tác giả | Phương pháp | Kết quả (đã tự kiểm chứng độc lập) | Ưu điểm | Nhược điểm |
|---|---|---|---|---|---|
| **VESTA** | Đề tài đang thực hiện | Pipeline point-in-time → kiểm định t bắt cặp + cluster-robust → điều tra outlier có căn cứ → DSR/PBO đầy đủ (7 cách xử lý dữ liệu) → audit regime × phân khúc sàn (đang triển khai) → PhoBERT (kế hoạch) → HybridACD (tạm hoãn) | n=15.081-15.084 sự kiện; toàn thị trường sau winsorize: Cohen's d=0,0729, DSR N=1/2/3 = 0,998/0,990/0,977 (vững); **riêng HOSE: DSR N=1/2/3 = 0,985/0,945/0,892 (KHÔNG vững ở N≥2)**; PBO=0,007 (rất thấp, đáng tin); sign-flip nghiêm trọng ở khủng hoảng 2022 (-5,14%) | Là nghiên cứu VN đầu tiên (đã khảo sát) áp dụng đầy đủ DSR/PBO; tự phát hiện và xử lý minh bạch lỗi dữ liệu (outlier thao túng giá XDC); phát hiện "Nghịch lý khả thi giao dịch" — đóng góp phản biện hiếm gặp trong literature VN | Effect size nhỏ ở dữ liệu thô; hiệu ứng không vững trên rổ HOSE (nhóm khả thi giao dịch nhất) ở N≥2; sign-flip theo regime chưa audit chéo với phân khúc sàn; phạm vi dữ liệu quốc tế có sẵn nhưng chưa tích hợp |

## 2.3 Nhận xét tổng hợp từ bảng so sánh

1. Không nghiên cứu VN nào đã khảo sát áp dụng kiểm định vững/DSR/PBO/audit theo regime — khoảng trống phương pháp luận rõ ràng nhất.
2. Cỡ mẫu của VESTA vượt trội tuyệt đối so với NEU-Stock (15.081 sự kiện so với 200 mẫu/1 mã) — nhưng cỡ mẫu lớn hơn cũng đòi hỏi thận trọng hơn (đúng bài học DSR).
3. FinDPO/RL-hierarchical cho kết quả ấn tượng nhưng đều trên thị trường Mỹ — bất kỳ kết quả nào VESTA đạt được trên VN30 đều là kiểm định mới, không phải tái lập.
4. HybridACD là phần mở rộng có căn cứ nhưng cần khiêm tốn về tình trạng chưa bình duyệt, khác biệt với phần lớn nguồn còn lại trong bảng.

---

# CHƯƠNG 3 — PHƯƠNG PHÁP NGHIÊN CỨU

## 3.1 Cách tiếp cận tổng thể

Nghiên cứu được thực hiện theo trình tự tuần tự nghiêm ngặt — mỗi bước chỉ bắt đầu khi bước trước đã có bằng chứng thực nghiệm xác nhận, tránh tình trạng phổ biến là xây dựng song song nhiều thành phần phức tạp trước khi biết chắc phần lõi (tín hiệu) có hoạt động hay không (nguyên tắc "Signal Before Infrastructure").

## 3.2 Phương pháp thu thập và xử lý dữ liệu

Thu thập tự động có kiểm soát lỗi và cơ chế thử lại; chuẩn hóa dữ liệu thô thành bảng có cấu trúc với đầy đủ nhãn thời gian sẵn có ngay từ thiết kế; kiểm tra tính toàn vẹn tham chiếu chéo giữa các nguồn trước khi sử dụng; lưu trữ dữ liệu thô song song với dữ liệu đã xử lý để không phải thu thập lại khi phát hiện nhu cầu mới.

## 3.3 Phương pháp kiểm định thống kê

- Kiểm định t bắt cặp làm phép kiểm định chính.
- Bootstrap theo cụm (cluster-robust) theo cả mã cổ phiếu và theo tháng, xử lý vấn đề các quan sát không độc lập hoàn toàn.
- Điều tra nguyên nhân cụ thể của giá trị bất thường (không loại bỏ mù quáng theo ngưỡng thống kê) — minh họa bằng việc truy tìm ra một sự kiện thao túng giá đơn lẻ (mã XDC, UPCOM, 5/2023) chiếm 97% độ lệch bất thường của toàn bộ phân phối.
- Khung lý thuyết Deflated Sharpe Ratio và Probability of Backtest Overfitting (Bailey & López de Prado), đối chiếu qua nhiều cách xử lý dữ liệu độc lập (dữ liệu thô, loại outlier, winsorize 0,5%/1%, cắt ngưỡng, tách riêng theo sàn giao dịch) để đảm bảo kết luận không phụ thuộc vào một lựa chọn xử lý cụ thể.
- Phân tích theo từng giai đoạn thị trường lịch sử có ranh giới xác định dựa trên sự kiện có thể kiểm chứng (khủng hoảng 2018, đại dịch 2020, khủng hoảng bất động sản/trái phiếu 2022, giai đoạn phục hồi 2023-2024...), kết hợp phân khúc theo sàn giao dịch/thanh khoản (audit lưới hai chiều).

## 3.4 Phương pháp xây dựng mô hình học máy

Tinh chỉnh có giám sát trên mô hình ngôn ngữ nhỏ tiếng Việt đã huấn luyện trước, ràng buộc rõ ràng về tài nguyên phần cứng; cân nhắc mở rộng sang tinh chỉnh theo sở thích trực tiếp (ưu tiên dự đoán có tương quan đúng hướng với lợi nhuận thực tế) nếu thời gian cho phép, lấy cảm hứng từ FinDPO nhưng với lưu ý rõ ràng đây là kiểm định mới trên VN30, không phải tái lập kết quả đã có trên S&P 500.

## 3.5 Phương pháp kiểm chứng tính nhất quán (nếu được tích hợp)

Áp dụng cơ chế can thiệp tại bước trích xuất xác suất cuối cùng của mô hình, ép buộc xác suất đầu ra tuân thủ các quy tắc toán học cơ bản của lý thuyết xác suất, không cần huấn luyện lại mô hình — kèm một bước "phiên dịch" kỹ thuật riêng vì mô hình phân loại cảm xúc (đầu ra vài lớp cố định) khác về bản chất kiến trúc so với mô hình sinh văn bản tự do mà khung lý thuyết gốc đã thử nghiệm.

## 3.6 Phương pháp đánh giá và kỷ luật khoa học

Mọi kết quả số liệu phải đi kèm bằng chứng thực nghiệm thực tế có thể tái lập được; mọi giả định quan trọng phải được ghi chép kèm căn cứ; tuân thủ kỷ luật "một hạng mục công việc tại một thời điểm" (WIP=1) — nguyên tắc này vừa được phát hiện vi phạm và sửa chữa trong quá trình thực hiện đề tài (18 hạng mục công việc phụ trợ chạy song song trong khi nút thắt khoa học chính bị bỏ ngỏ), là một minh chứng thực tế cho quy trình tự kiểm tra chéo được áp dụng nghiêm túc.

---

# CHƯƠNG 4 — KẾT QUẢ MONG ĐỢI

## 4.1 Kết quả mong đợi về hạ tầng dữ liệu

**Mong đợi:** kho dữ liệu tài chính-tin tức Việt Nam đúng-thời-điểm, quy mô vượt trội các bộ dữ liệu học thuật VN đã công bố.
**Tiêu chí:** không rò rỉ thông tin tương lai; độ phủ >1.000 mã có sự kiện gắn giá; tỷ lệ toàn văn >90%.
**Tình trạng:** đã đạt ở phần lõi; phần mở rộng đang chờ kiểm tra chất lượng độc lập.

## 4.2 Kết quả mong đợi về giả thuyết tín hiệu cốt lõi (H1)

**Giả thuyết H1:** sau tin tức tiêu cực, giá cổ phiếu giảm nhẹ ngắn hạn rồi phục hồi một phần trung hạn.

| Mức độ | Tiêu chí | Tình trạng |
|---|---|---|
| Tối thiểu | Ý nghĩa thống kê trên mẫu lớn | Đã đạt (nhưng không đủ, dễ ảo giác cỡ mẫu lớn) |
| Trung bình | Vững sau cluster-robust và DSR/PBO (N=1,2,3) trên toàn thị trường | Đã đạt sau xử lý outlier |
| Cao | Vững trên riêng rổ HOSE VÀ không đảo dấu theo regime | **Chưa đạt** — đang audit (Chương 3.3) |
| Thay thế | Tín hiệu có điều kiện (theo regime/thanh khoản) | Khả năng cao nhất theo bằng chứng hiện có — vẫn là đóng góp khoa học giá trị |

## 4.3 Kết quả mong đợi từ mô hình PhoBERT tinh chỉnh

Đạt độ chính xác tương đương/vượt các nghiên cứu VN đã khảo sát (81-93%); khi thay thế từ điển quy tắc bằng điểm số mô hình trong backtest, hiệu ứng không yếu đi đáng kể. **Cảnh báo:** accuracy cao không tự động đảm bảo giá trị giao dịch (bài học từ Preprints.org 2023) — luôn cần backtest tái xác nhận, không dừng ở báo cáo độ chính xác phân loại.

## 4.4 Kết quả mong đợi từ lớp kiểm chứng tính nhất quán (nếu tích hợp)

Đảm bảo toán học 100% các cặp dự đoán liên quan tuân thủ quy tắc xác suất cơ bản, không giảm chất lượng dự báo. **Kỳ vọng thận trọng:** không mặc định đạt đúng con số của HybridACD gốc (khác kiến trúc mô hình: classification-head so với autoregressive LLM).

## 4.5 Kết quả mong đợi về đóng góp khoa học tổng thể (độc lập với kết quả H1)

1. Đóng góp phương pháp luận: nghiên cứu VN đầu tiên (đã khảo sát) áp dụng đầy đủ DSR/PBO.
2. Đóng góp thực nghiệm phụ: phát hiện "Nghịch lý khả thi giao dịch".
3. Đóng góp về minh bạch quy trình: ghi chép công khai cả sai sót đã phát hiện và sửa.
4. Đóng góp mở rộng lý thuyết (nếu tích hợp HybridACD): áp dụng khung tính nhất quán xác suất vào bối cảnh tài chính cụ thể.

---

# CHƯƠNG 5 — KẾ HOẠCH THỰC HIỆN CHI TIẾT (13 GIAI ĐOẠN)

| # | Giai đoạn | Tình trạng |
|---|---|---|
| 1 | Xác định vấn đề nghiên cứu và tổng quan tài liệu | Đã hoàn thành phần lớn |
| 2 | Thiết kế kiến trúc hệ thống và kỷ luật quy trình nghiên cứu | Đã hoàn thành |
| 3 | Thu thập dữ liệu nền tảng: danh mục mã và giá giao dịch | Đã hoàn thành |
| 4 | Thu thập tin tức tài chính và mở rộng kho văn bản vĩ mô | Đã hoàn thành phần cốt lõi; phần mở rộng cần kiểm tra chất lượng độc lập |
| 5 | Thu thập báo cáo tài chính và sự kiện doanh nghiệp | Đã hoàn thành |
| 6 | Kiểm tra chất lượng toàn diện và tích hợp chéo | Đã hoàn thành |
| 7 | Ghép nối dữ liệu đúng thời điểm | Đã hoàn thành |
| 8 | Kiểm định thống kê cơ bản của giả thuyết tín hiệu | Đã hoàn thành |
| 9 | Kiểm định vững, khử outlier, phân biệt tín hiệu thật với ảo giác thống kê | Đã hoàn thành phần cốt lõi |
| 10 | Audit tính ổn định theo giai đoạn thị trường và phân khúc thanh khoản | **Đang triển khai — ưu tiên cao nhất hiện tại** |
| 11 | Xây dựng và tinh chỉnh mô hình ngôn ngữ nhỏ | Chưa bắt đầu — phụ thuộc Giai đoạn 10 |
| 12 | Tích hợp lớp kiểm chứng tính nhất quán (tùy chọn) | Tạm hoãn |
| 13 | Tổng hợp kết quả, viết báo cáo khóa luận | Chưa bắt đầu chính thức |

**Ghi chú tiến độ:** 9/13 giai đoạn đã hoàn thành hoặc gần hoàn thành; phần lớn khối lượng kỹ thuật nặng nhất đã xong; cần dành đủ thời gian dự phòng cho Giai đoạn 11 (thường đòi hỏi nhiều thử nghiệm lặp lại trên phần cứng giới hạn), không dồn vào giai đoạn viết báo cáo cuối.

**Bài học quy trình quan trọng đã rút ra trong quá trình thực hiện:** một đợt kiểm tra chéo gần đây phát hiện 18 hạng mục công việc phụ trợ (mở rộng nguồn tin tức vĩ mô) đang được tiến hành song song trong khi Giai đoạn 10 — nút thắt khoa học quyết định — bị bỏ ngỏ, vi phạm nguyên tắc "một hạng mục tại một thời điểm" đã đặt ra từ Giai đoạn 2. Đã điều chỉnh: tạm dừng các hạng mục phụ trợ, ưu tiên tuyệt đối cho Giai đoạn 10. Đây là minh chứng cho cơ chế tự kiểm tra chéo hoạt động đúng chức năng của nó trong suốt quá trình nghiên cứu.

---

# CHƯƠNG 6 — DỰ KIẾN BỐ CỤC KHÓA LUẬN HOÀN CHỈNH

1. Mở đầu (tính cấp thiết, mục tiêu, phạm vi, đối tượng, phương pháp, kết quả mong đợi)
2. Cơ sở lý thuyết và tổng quan tài liệu
3. Thiết kế dữ liệu và hạ tầng nghiên cứu
4. Kiểm định giả thuyết tín hiệu và kỷ luật thống kê
5. Mô hình ngôn ngữ và (nếu có) lớp kiểm chứng tính nhất quán
6. Kết quả và thảo luận
7. Kết luận, hạn chế, và hướng phát triển
Tài liệu tham khảo — Phụ lục (mã nguồn, bảng số liệu chi tiết, lệnh chạy tái lập)

---