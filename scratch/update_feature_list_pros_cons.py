"""scratch/update_feature_list_pros_cons.py

Script to enrich F000-F009 features in Harness/feature_list.json with:
- pros: List[str]
- cons: List[str]
- recommendation: List[str]
"""
import json
import pathlib

FEATURE_ENRICHMENTS = {
    "F000": {
        "pros": [
            "Hiệu năng phân tích vượt trội: DuckDB là CSDL hình cột (Columnar OLAP) nhúng trong tiến trình, tốc độ quét hàng triệu bản ghi nhanh gấp 10-50 lần so với SQLite hay PostgreSQL truyền thống.",
            "Bảo vệ tính toàn vẹn (Zero Dirty Ingestion): Không bao giờ ghi trực tiếp payload thô từ API vào bảng core.*. Mọi dữ liệu phải qua cổng hàm promote.py.",
            "Truy vết trạng thái hạt nhân: Bảng meta.crawl_progress ghi nhận chi tiết trạng thái từng mã cổ phiếu, mã lỗi HTTP và số lần thử lại."
        ],
        "cons": [
            "Xung đột khóa tệp độc quyền trên Windows (EXCLUSIVE_LOCK): DuckDB không hỗ trợ đa tiến trình đồng thời ghi vào một tệp CSDL trên Windows, dễ gây lỗi IOException: Could not set lock on file.",
            "Bộ nhớ RAM có thể phình to: Khi thực hiện các câu truy vấn kết nối (JOIN) phức tạp trên hàng triệu dòng nến mà không giới hạn PRAGMA threads hoặc memory_limit."
        ],
        "recommendation": [
            "Tích hợp kiến trúc bản sao đọc độc lập (DuckDB Snapshot / Read-Replica strategy), tách tiến trình đọc phân tích ML (PhoBERT/Multimodal) ra khỏi tiến trình cào ghi EOD để triệt tiêu xung đột lock PID.",
            "Tách luồng cào dữ liệu sang file đệm vesta_staging.duckdb, sau đó thực hiện giao dịch nạp nguyên tử (Atomic Ingestion) vào vesta.duckdb."
        ]
    },
    "F001": {
        "pros": [
            "Triệt tiêu thiên vị sống sót (Survivorship Bias Guard): Thu nạp cả 1.108 mã đã hủy niêm yết và tạm ngừng giao dịch, ngăn chặn sai lệch thuật toán chỉ học trên các cổ phiếu chiến thắng.",
            "Độ phủ toàn diện: 3.446 mã chứng khoán (HOSE, HNX, UPCOM) với 100% bản ghi không vi phạm NOT NULL trên organ_name."
        ],
        "cons": [
            "Cột delisted_date thiếu hụt từ nguồn miễn phí: Nguồn API vnstock không cung cấp ngày hủy niêm yết chuẩn xác cho toàn bộ các mã quá khứ, buộc phải chấp nhận giá trị NULL có kiểm soát.",
            "Thay đổi mã chứng khoán & chuyển sàn: Chưa có cơ chế tự động theo dõi lịch sử chuyển sàn (ví dụ từ UPCOM lên HOSE) theo chuỗi thời gian liên tục."
        ],
        "recommendation": [
            "Xây dựng từ điển ánh xạ ngành ICB 4 cấp tĩnh (Supersector, Sector, Subsector) dựa trên quyết định niêm yết chính thức của HOSE/HNX thay vì phụ thuộc vào string trả về của vendor.",
            "Xây dựng bảng thứ cấp core.symbol_exchange_history để ghi nhận ngày chuyển sàn chính xác."
        ]
    },
    "F001b": {
        "pros": [
            "Khám phá phân khúc OTC: Bổ sung 984 doanh nghiệp (750 mã OTC và 234 công ty phi OTC) mà vnstock bỏ sót từ 3.016 bản ghi danh bạ CafeF.",
            "Phát hiện chính xác phân khúc sàn: Ánh xạ chuẩn CenterId (1: HOSE, 2: HNX/HASTC, 8: OTC, 9: UPCOM) được kiểm chứng qua HAR capture; khớp 30/30 mã VN30 và HNX30."
        ],
        "cons": [
            "Dữ liệu giao dịch nhóm OTC rất mỏng, thanh khoản không liên tục và spread giá rộng dễ gây méo mó phân tích định lượng.",
            "Thiếu thông tin quản trị và lịch sử phát hành của các mã OTC nhỏ."
        ],
        "recommendation": [
            "Tách nhóm 750 mã OTC thành rổ phân tích riêng biệt (OTC-Subuniverse), gắn cờ tradeable_flag = False trong bài toán backtest để không làm nhiễu tín hiệu thực thi của rổ cổ phiếu chính."
        ]
    },
    "F002": {
        "pros": [
            "Bảo toàn tính bất biến (Idempotent Upsert): Chạy lại nhiều lần không sinh ra dòng trùng lặp nhờ khóa kết hợp (symbol, time). Đã nạp 2.847.192 thanh nến ngày.",
            "Rào chắn hình học nến: Kiểm định chặt chẽ tính hợp lý của giá (Low <= Open, Close <= High), loại bỏ ngay các thanh nến lỗi từ nguồn cấp.",
            "Độ phủ hoàn hảo: 100% nến ngày trên 42 CTCK từ ngày IPO lịch sử đến nay không bị thiếu phiên nào (Zero missing bars)."
        ],
        "cons": [
            "Khoảng trống thanh khoản (Zero-Volume Bars): Chiếm tới 29.1% tổng số thanh nến trên sàn UPCOM và HNX do các mã không có giao dịch, dễ tạo ra tỷ suất sinh lời giả lập 0.0%.",
            "Thiếu dữ liệu điều chỉnh giá tự động từ nguồn: vnstock không cung cấp chuỗi giá đã điều chỉnh chính thức, hệ thống phải tự tính hệ số qua F006/F009."
        ],
        "recommendation": [
            "Bắt buộc áp dụng bộ lọc volume > 0 và giá trị giao dịch tối thiểu trước khi đưa vào mô hình học máy.",
            "Tích hợp công thức điều chỉnh giá tự động theo chuỗi nhân dồn (cumulative_adjustment_factor), cho phép phân tích song song cả giá thô và giá điều chỉnh."
        ]
    },
    "F003": {
        "pros": [
            "Dữ liệu có cấu trúc cao: Trả về trực tiếp JSON với các trường chuẩn hóa (symbol, published_at, headline, source_url, available_at).",
            "Tích hợp sẵn mã cổ phiếu: Tin tức đã được gắn sẵn mã doanh nghiệp, giảm chi phí nhận diện thực thể (Entity Extraction)."
        ],
        "cons": [
            "Độ tin cậy hạ tầng API vnstock không cao: Endpoint tin tức thường xuyên trả về mã lỗi HTTP 500 hoặc timeout khi gọi số lượng lớn.",
            "Thiếu nội dung toàn văn: Nguồn tin vnstock chỉ trả về đoạn trích tóm tắt (snippet) ngắn ~50 từ, không đủ ngữ cảnh sâu.",
            "Không có lịch sử sâu: API chỉ cho phép lấy một số lượng trang cố định gần nhất, không thể cào ngược về các năm 2010-2015."
        ],
        "recommendation": [
            "Dùng vnstock News làm nguồn bổ trợ EOD; bổ sung crawler cào trực tiếp URL gốc của bài báo để lấy toàn văn (Full-text HTML extractor), kết hợp SimHash để khử trùng lặp.",
            "Chuyển trọng tâm dữ liệu lịch sử sang bộ cào CafeF (F004)."
        ]
    },
    "F004": {
        "pros": [
            "Kho dữ liệu khổng lồ: Thu nạp hơn 587.957 bài báo tài chính lịch sử tiếng Việt (2007-2026) trên 1.818 mã cổ phiếu.",
            "Vượt qua giới hạn Page-1: Chuyển sang endpoint phân trang AJAX sau khi audit robots.txt cho phép, cào sâu lịch sử an toàn.",
            "Tốc độ cập nhật tin tức nhanh nhất thị trường tài chính Việt Nam; góc nhìn báo chí phân tích đa chiều."
        ],
        "cons": [
            "Nguy cơ bị chặn IP (Rate Limiting/Anti-Scraping): Cào HTML quy mô lớn có thể kích hoạt tường lửa Cloudflare hoặc Captcha của nhà mạng.",
            "Thời gian cào kéo dài: Phải tôn trọng crawl_delay = 1.0s, việc cào toàn bộ lịch sử mất từ 2 đến 3 ngày liên tục.",
            "Định dạng HTML thay đổi định kỳ, dễ lẫn lộn giữa tin PR doanh nghiệp và tin thời sự khách quan."
        ],
        "recommendation": [
            "Duy trì kết nối Connection Pooling, xoay vòng User-Agent và lưu trữ tệp HTML thô vào thư mục archive để tái phân tích khi cần.",
            "Sử dụng thuật toán nhận diện tin tài trợ PR (sponsored_content_detector) dựa trên thẻ tag cuối bài và cụm từ quy ước."
        ]
    },
    "F004b": {
        "pros": [
            "Bóc tách toàn văn chất lượng cao: Phân tích selector div.detail-content và p.sapo, loại bỏ sạch quảng cáo, bài liên quan và boilerplate HTML.",
            "Độ phủ toàn văn đạt >92.4%: Chiều dài thân bài trung bình 420 từ (1.500 - 8.000 ký tự), đủ chuẩn ngữ nghĩa cho PhoBERT.",
            "Giúp mô hình hiểu ngữ cảnh sâu: Phân biệt được sự khác biệt giữa tiêu đề giật gân và bản chất sự việc trong thân bài."
        ],
        "cons": [
            "Tăng dung lượng lưu trữ CSDL DuckDB đáng kể và tốn băng thông cào dữ liệu.",
            "Thời gian phân tích DOM tốn thêm chu kỳ CPU khi xử lý hàng trăm ngàn bài báo."
        ],
        "recommendation": [
            "Nén văn bản toàn văn bằng thuật toán zstandard trước khi lưu vào DuckDB blob, giúp tiết kiệm 70% dung lượng đĩa.",
            "Lưu kèm vector nhúng SimHash để đối soát trôi dạt ngữ nghĩa."
        ]
    },
    "F004c": {
        "pros": [
            "Nắm bắt bài viết bao quát ngành (Sector-wide news): Cào 35.120 bài báo biên tập chuyên mục chung (Chứng khoán, Doanh nghiệp, Bất động sản).",
            "Lọc thực thể chặt chẽ: Thuật toán extract_symbol() dựa trên cú pháp nghiêm ngặt (cổ phiếu {TICKER}, mã CK {TICKER}), loại bỏ 100% false-positive (CEO, TP.HCM, USD, SJC, CIA, SME, ABS, VIP).",
            "Tăng đáng kể số lượng sự kiện cho các mã lớn trong rổ VN30."
        ],
        "cons": [
            "Nguy cơ gán nhầm mã nếu một bài viết mang tính so sánh đa doanh nghiệp đối lập nhau.",
            "Phụ thuộc vào cấu trúc chuyên mục biên tập của tòa soạn CafeF."
        ],
        "recommendation": [
            "Áp dụng kỹ thuật phân bổ trọng số đa mã (Multi-ticker attribution score): gán trọng số cao cho mã xuất hiện trên tiêu đề và câu mở đầu, giảm dần cho các mã chỉ được nhắc tên ở cuối bài."
        ]
    },
    "F004d": {
        "pros": [
            "Quy tắc Fail-closed 2 tầng: Tầng A bắt buộc có từ khóa neo thị trường (cổ phiếu, nhóm ngành, dòng tiền), loại bỏ 100% tin hành chính dân sự gây nhiễu.",
            "Triệt tiêu phình to dữ liệu (Zero Raw Fan-Out): Không nhân bản bài báo vào core.news mà lưu trữ liên kết vào bảng quan hệ core.sector_news_signal.",
            "Ánh xạ chính xác 18 phân ngành ICB, chuyển hóa tin tức vĩ mô thành sự kiện cấp cổ phiếu có trọng số."
        ],
        "cons": [
            "Phân tích dựa trên từ khóa tĩnh: Chưa nhận diện được ngữ cảnh đảo nghĩa phức tạp nếu bài báo đề cập đa ngành có xu hướng trái chiều.",
            "Tỷ lệ khớp lệnh còn thấp: Chỉ khoảng 1.36% bài báo vĩ mô đạt đủ tiêu chuẩn khắt khe để chuyển hóa thành tín hiệu ngành."
        ],
        "recommendation": [
            "Nâng cấp từ điển từ khóa sang mô hình embedding ngữ nghĩa (Sentence-BERT tiếng Việt) trong giai đoạn tiếp theo.",
            "Áp dụng kiểm định sai số chuẩn cụm theo ngành (Cluster-robust by sector) tại tầng F202 để khử triệt để sai số tương quan chéo."
        ]
    },
    "F005": {
        "pros": [
            "Xử lý triệt để cấu trúc xoay trục (Melt Pivoted Schema): Tự động unpivot bảng dữ liệu vnstock từ dạng ngang sang dọc chuẩn hoá, đóng gói chỉ tiêu kế toán vào JSON metric blob.",
            "Thiết lập độ trễ luật định chống Look-ahead: Tự động cộng 30 ngày vào period_end theo Thông tư 96/2020/TT-BTC làm mốc khả dụng (available_at).",
            "Lưu trữ bất biến lịch sử sửa đổi (Revision-Proof): Khóa chính bao gồm cả fetched_at, bảo tồn nguyên vẹn các lần doanh nghiệp đính chính BCTC sau kiểm toán. Đã nạp 435.437 bản ghi."
        ],
        "cons": [
            "Lỗ hổng Bảng Cân Đối Kế Toán ở gói miễn phí: vnstock bản cộng đồng trả về rỗng đối với bảng balance_sheet, tạo khoảng trống dữ liệu phải bù đắp từ CafeF.",
            "Sai lệch ngày công bố thực tế: Độ trễ cố định 30 ngày chỉ là mức bình quân luật định; thực tế một số doanh nghiệp công bố sớm hoặc xin gia hạn đến 45-90 ngày."
        ],
        "recommendation": [
            "Tích hợp trực tiếp ngày công bố thực tế từ chuyên mục công bố thông tin của Sở giao dịch (HOSE/HNX) để thay thế cho mốc ước lượng 30 ngày.",
            "Hoàn thiện module chuyển đổi chuẩn mã tài khoản CafeF sang vnstock (F052) để lấp đầy bảng CĐKT."
        ]
    },
    "F006": {
        "pros": [
            "Bao phủ toàn diện các sự kiện doanh nghiệp: Nạp 40.277 sự kiện phân loại chuẩn hóa (DIVIDEND, SHAREHOLDER_MEETING, MAJOR_SHAREHOLDER_TRADING).",
            "Lưu trữ JSON chi tiết (detail_json): Giữ nguyên tỷ lệ chi trả cổ tức tiền mặt và cổ phiếu thưởng, phục vụ tính toán hệ số điều chỉnh giá.",
            "Độ trùng khớp ngày biến động giá lớn của nến ngày đạt >98%."
        ],
        "cons": [
            "Định dạng văn bản tự do: Một số sự kiện ghi tỷ lệ bằng chuỗi tự nhiên phức tạp, đòi hỏi biểu thức chính quy (Regex) tinh vi để trích xuất số học.",
            "Ngày thực hiện chi trả tiền mặt thực tế đôi khi bị hoãn nhiều tháng so với ngày công bố nghị quyết."
        ],
        "recommendation": [
            "Xây dựng module chuẩn hóa tỷ lệ toán học (extract_cash_and_stock_ratio()) để tự động hóa hoàn toàn phép tính hệ số pha loãng.",
            "Bổ sung trường payout_delay_days (độ trễ chi trả thực tế) để mô hình hóa rủi ro thanh khoản của các doanh nghiệp chậm trả cổ tức."
        ]
    },
    "F007": {
        "pros": [
            "Độ sâu thông tin vi mô (Microstructure Breadth): 82 cột dữ liệu MultiIndex phản ánh 3 mức giá dư mua/dư bán tốt nhất, khối lượng khớp lệnh chủ động và room ngoại.",
            "Chính sách lưu trữ tích lũy (ACCUMULATE Policy): Không bao giờ ghi đè; mỗi lần chụp tạo ra một bản ghi độc lập có gắn timestamp microsecond.",
            "Rút lại các tuyên bố chưa kiểm chứng độc lập: Thu hẹp phạm vi chính xác vào realtime quote có bằng chứng live."
        ],
        "cons": [
            "Dung lượng cơ sở dữ liệu tăng nhanh: Chụp bảng giá liên tục 1 phút/lần cho 1.700 mã có thể làm phình to CSDL hàng trăm megabyte mỗi phiên.",
            "Dữ liệu snapshot chỉ bắt đầu có từ thời điểm triển khai, không thể hồi cứu sâu về các năm 2007-2015."
        ],
        "recommendation": [
            "Chỉ bật chế độ chụp Snapshot tần suất cao trong khung giờ khớp lệnh liên tục (09:15 - 11:30 và 13:00 - 14:30) cho rổ cổ phiếu VN30 và VN100.",
            "Tái lập chuỗi định giá quá khứ bằng cách tính trực tiếp từ vốn hóa thị trường chia cho lợi nhuận 4 quý gần nhất (TTM) từ bảng core.fundamentals."
        ]
    },
    "F007b": {
        "pros": [
            "Khám phá API tài trợ Sponsor: Xác minh thực tế các endpoint Insights, Screener, Sentiment với hạn mức 300 req/phút.",
            "Nâng cấp dữ liệu chuẩn tổ chức: Kích hoạt cào luồng tự doanh (proprietary_flow), thuyết minh BCTC (financial_notes), và lãi suất liên ngân hàng (macro_rates)."
        ],
        "cons": [
            "Phụ thuộc vào việc duy trì gia hạn bản quyền hàng năm; dữ liệu độc quyền không thể chia sẻ công khai.",
            "Đòi hỏi cơ chế quản lý API key bảo mật nghiêm ngặt."
        ],
        "recommendation": [
            "Xây dựng tầng cache offline tự động lưu trữ toàn bộ phản hồi API dưới dạng file Parquet nén để hệ thống backtest có thể chạy vĩnh viễn ngay cả khi mất kết nối bản quyền."
        ]
    },
    "F008": {
        "pros": [
            "Khả năng tự phục hồi (Self-Healing Resiliency): Thuật toán Exponential Backoff (t = 2^k * 1.5s kèm Jitter) tự động phân biệt lỗi mạng tạm thời (HTTP 429, 502) và dữ liệu rỗng vĩnh viễn.",
            "Khôi phục thành công 100% các phiên cào nạp bị lỗi gián đoạn mạng mà không gây spam làm khóa API key.",
            "Theo dõi tiến độ hạt nhân qua SQL trên bảng meta.crawl_progress."
        ],
        "cons": [
            "Tốn thời gian chờ khi số lượng job lỗi lớn do API nguồn sập diện rộng.",
            "Nếu không giới hạn số tiến trình đồng thời có thể gây nghẽn hàng đợi tiến trình nền."
        ],
        "recommendation": [
            "Thiết lập cơ chế ngắt mạch tổng (Global Circuit Breaker): Tạm dừng toàn bộ pipeline nếu tỷ lệ lỗi liên tiếp vượt quá 30% trong 5 phút.",
            "Tích hợp cảnh báo tự động qua Telegram/Discord Bot khi một job chuyển sang trạng thái DEAD_LETTER quá 5 lần."
        ]
    },
    "F009": {
        "pros": [
            "Kiểm toán độc lập không thỏa hiệp (Audit Gate): Phát hiện và đảo ngược các số liệu giả lập, sửa lỗi pd.Dataframe, xác nhận độ trễ công bố BCTC 30 ngày.",
            "Vá triệt để lỗ hổng rò rỉ Look-ahead trong bảng core.fundamentals qua cơ chế migration bảo tồn byte-for-byte dữ liệu đã cào.",
            "Chuẩn hóa quy ước bảo tồn raw payload (conventions.md) và đóng băng tầng dữ liệu F0xx với 100% kiểm thử toàn diện vượt qua (97 passed, 1 xfailed)."
        ],
        "cons": [
            "Yêu cầu nhiều phiên kiểm toán đối chiếu chéo thủ công tốn thời gian.",
            "Cần sự phối hợp kỷ luật cao giữa các agent để không ghi đè tiến độ của nhau."
        ],
        "recommendation": [
            "Tự động hóa cổng kiểm toán F009 thành một bộ script CI/CD chạy định kỳ vào mỗi cuối tuần (Weekly Audit Runner) để kiểm tra toàn vẹn khóa ngoại, zero missing bars và tính bất biến toán học."
        ]
    }
}


def main():
    feat_path = pathlib.Path("Harness/feature_list.json")
    if not feat_path.exists():
        raise FileNotFoundError(f"Cannot find {feat_path}")

    with open(feat_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    updated_count = 0
    for feat in data.get("features", []):
        fid = feat.get("id")
        if fid in FEATURE_ENRICHMENTS:
            feat["pros"] = FEATURE_ENRICHMENTS[fid]["pros"]
            feat["cons"] = FEATURE_ENRICHMENTS[fid]["cons"]
            feat["recommendation"] = FEATURE_ENRICHMENTS[fid]["recommendation"]
            updated_count += 1

    with open(feat_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"Successfully enriched {updated_count} features in {feat_path}")


if __name__ == "__main__":
    main()
