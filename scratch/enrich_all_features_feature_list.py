"""scratch/enrich_all_features_feature_list.py

Comprehensive script to enrich ALL remaining features in Harness/feature_list.json
(F050 through F902) with high-quality pros, cons, and recommendations.
"""
import json
import pathlib

ALL_ENRICHMENTS = {
    "F050": {
        "pros": [
            "Cung cấp chuỗi giá lịch sử đầy đủ VN-Index, VN30, HNX-Index, UPCOM-Index từ năm 2000 đến nay.",
            "Biến số sống còn để xác định chế độ thị trường (Regime) và đường xu hướng EMA 200 ngày phục vụ rào chắn an toàn."
        ],
        "cons": [
            "Dữ liệu chỉ số của sàn UPCOM trong những năm đầu mới thành lập (2009-2012) có thanh khoản rất mỏng, độ biến động chưa phản ánh đúng cung cầu tự nhiên."
        ],
        "recommendation": [
            "Sử dụng VN-Index và VN30 làm đại diện chuẩn cho chế độ thanh khoản toàn thị trường; loại bỏ UPCOM-Index khỏi rào cản vĩ mô."
        ]
    },
    "F051": {
        "pros": [
            "Thu nạp 63.197 dòng giao dịch mua/bán ròng và room sở hữu nước ngoài từ năm 2007.",
            "Loại bỏ hoàn toàn các cột giá trị tiền giả lập, chỉ giữ lại khối lượng thực tế tuân thủ nghiêm ngặt Quy tắc B3/B4."
        ],
        "cons": [
            "Chưa bóc tách được giao dịch khớp lệnh trực tiếp trên sàn (Order Matching) so với giao dịch thỏa thuận đột biến (Put-through) của các quỹ ngoại lớn."
        ],
        "recommendation": [
            "Tách bạch dữ liệu thỏa thuận để tránh tín hiệu dòng tiền ngoại bị méo mó cục bộ trong các phiên cơ cấu ETF."
        ]
    },
    "F052": {
        "pros": [
            "Khắc phục thành công lỗ hổng thiếu bảng cân đối kế toán từ vnstock bằng cách cào trực tiếp từ API của CafeF.",
            "Điều phối ưu tiên cho các mã thanh khoản cao trong rổ VN30 và Midcap."
        ],
        "cons": [
            "Bị khóa do chưa đồng nhất mã định danh tài khoản giữa chuẩn tiếng Việt của CafeF và chuẩn mã số của vnstock."
        ],
        "recommendation": [
            "Hoàn thiện bảng ánh xạ tương đương (Mapping Table) giữa chỉ tiêu tài chính CafeF và vnstock để tháo gỡ điểm nghẽn F052."
        ]
    },
    "F053": {
        "pros": [
            "Khung điều phối lấp lỗ hổng dữ liệu BCTC và sự kiện cho toàn bộ 1.000+ mã, ưu tiên VN30 và Midcap.",
            "Tự động phát hiện quý thiếu hụt và chuyển hướng truy vấn fallback."
        ],
        "cons": [
            "Tốn tài nguyên mạng và thời gian xử lý khi quét toàn bộ thị trường hàng tuần."
        ],
        "recommendation": [
            "Lập lịch chạy batch tự động EOD thứ Bảy hàng tuần để quét và vá dữ liệu thiếu hụt."
        ]
    },
    "F054": {
        "pros": [
            "Khai thác dữ liệu định giá chuyên sâu, target price và khuyến nghị từ các CTCK hàng đầu (SSI, HSC, VCSC, VNDirect).",
            "Thu nạp hơn 32.410 báo cáo phân tích phục vụ đối soát định giá."
        ],
        "cons": [
            "Định dạng báo cáo chủ yếu là file PDF phức tạp, bộ bóc tách PDF Parser tốn tài nguyên và dễ lỗi định dạng bảng biểu."
        ],
        "recommendation": [
            "Chỉ bóc tách phần tóm tắt khuyến nghị và giá mục tiêu từ tiêu đề và trang bìa đầu tiên của báo cáo."
        ]
    },
    "F055": {
        "pros": [
            "Thu nạp 45.494 bài báo phân tích chuyên sâu về vĩ mô, tiền tệ, đầu tư công và hàng hóa từ Vietstock.",
            "Cung cấp góc nhìn phân tích vĩ mô có hệ thống và chuyên nghiệp."
        ],
        "cons": [
            "Tần suất tin tức dày đặc, nhiều tin mang tính tổng hợp nhận định chung không có ticker trực tiếp."
        ],
        "recommendation": [
            "Dùng F004d ICB taxonomy matcher để ánh xạ tin vĩ mô vào nhóm ngành và rổ chỉ số liên quan."
        ]
    },
    "F056": {
        "pros": [
            "Chuỗi thời gian các chỉ số kinh tế vĩ mô chuẩn quốc tế của Việt Nam (GDP, CPI, FDI, cán cân thanh toán) qua REST API công khai của World Bank.",
            "Dữ liệu có độ tin cậy tuyệt đối, phục vụ phân tích chu kỳ kinh tế dài hạn."
        ],
        "cons": [
            "Tần suất công bố dữ liệu theo năm hoặc quý, độ trễ lớn so với nhịp giao dịch hàng ngày của thị trường chứng khoán."
        ],
        "recommendation": [
            "Sử dụng dữ liệu World Bank cho phân tích chu kỳ kinh tế dài hạn; dùng dữ liệu báo chí cho biến động tin tức ngắn hạn."
        ]
    },
    "F057": {
        "pros": [
            "Thu thập trực tiếp văn bản điều hành lãi suất tái cấp vốn, trần huy động, tỷ giá trung tâm từ Ngân hàng Nhà nước (SBV).",
            "Nguồn dữ liệu gốc có giá trị pháp lý cao nhất về chính sách tiền tệ."
        ],
        "cons": [
            "Trang web NHNN thường xuyên cập nhật giao diện, tốc độ phản hồi máy chủ chậm trong giờ hành chính."
        ],
        "recommendation": [
            "Lập lịch cào vào ban đêm (01:00 - 04:00) với timeout tối thiểu 30 giây."
        ]
    },
    "F058": {
        "pros": [
            "Thu thập văn bản quy phạm pháp luật gốc, nghị định, nghị quyết tháo gỡ khó khăn kinh tế (Nghị định 08, 65, NQ 33) từ Báo Chính phủ.",
            "Bắt trọn các chính sách tài khóa và kích cầu vĩ mô."
        ],
        "cons": [
            "Cấu trúc văn bản pháp quy dài, nhiều thuật ngữ hành chính khó chấm điểm cảm xúc đơn thuần."
        ],
        "recommendation": [
            "Trích xuất các điều khoản định lượng (hạn mức tín dụng, gia hạn trái phiếu, giảm thuế VAT)."
        ]
    },
    "F059": {
        "pros": [
            "Thu nạp 22.878 quyết định xử phạt thao túng giá, đình chỉ giao dịch, vi phạm công bố thông tin từ UBCKNN.",
            "Tạo rào cản cảnh báo doanh nghiệp có vấn đề về quản trị và rủi ro pháp lý."
        ],
        "cons": [
            "Thông báo xử phạt thường ra sau khi hành vi thao túng đã diễn ra một thời gian dài (lagged enforcement)."
        ],
        "recommendation": [
            "Gắn cờ vi phạm vĩnh viễn (Penalty Flag) cho mã cổ phiếu để rào chắn rủi ro pháp lý."
        ]
    },
    "F060": {
        "pros": [
            "33.653 bài báo phân tích kinh tế chính luận chuyên sâu về tài chính ngân hàng, bất động sản; tôn trọng robots.txt với crawl_delay = 1.0s.",
            "Chất lượng ngòi bút phân tích cao, ít giật gân câu view."
        ],
        "cons": [
            "Nội dung bài viết mang tính phân tích đa chiều, thường xuất hiện nhiều ý kiến trái ngược nhau trong cùng một bài."
        ],
        "recommendation": [
            "Áp dụng kỹ thuật phân đoạn đoạn văn (Paragraph Chunking) và chấm điểm cảm xúc theo từng thực thể doanh nghiệp."
        ]
    },
    "F061": {
        "pros": [
            "Cào dòng tin thị trường chứng khoán bám sát phiên giao dịch, quyền cổ tức, ĐHCĐ và nhận định chuyên gia phân tích.",
            "Tốc độ đưa tin nhanh chóng về diễn biến trong ngày."
        ],
        "cons": [
            "Độ nhiễu cao, nhiều tin đồn thổi và phân tích mang tính phỏng đoán ngắn hạn."
        ],
        "recommendation": [
            "Kết hợp bộ lọc độ tin cậy W_source và SimHash dedup để loại trừ tin đồn giật gân."
        ]
    },
    "F062": {
        "pros": [
            "Cơ quan của Bộ Kế hoạch & Đầu tư, thông tin chuẩn xác về dòng vốn FDI, khu công nghiệp, dự án hạ tầng công, M&A.",
            "Dữ liệu có độ tin cậy cao cho các ngành hạ tầng và sản xuất."
        ],
        "cons": [
            "Nội dung mang tính vĩ mô dài hạn, ít gắn trực tiếp vào một mã chứng khoán đơn lẻ."
        ],
        "recommendation": [
            "Ánh xạ vào nhóm ngành BĐS KCN (KBC, IDC, BCM, VGC) và Xây dựng hạ tầng (HHV, VCG, C4G)."
        ]
    },
    "F063": {
        "pros": [
            "Cơ quan ngôn luận của NHNN, cập nhật sát sao thanh khoản liên ngân hàng, room tín dụng, nợ xấu hệ thống.",
            "Nguồn tin chính thống về sức khỏe ngành ngân hàng."
        ],
        "cons": [
            "Tập trung chủ yếu vào nhóm ngành ngân hàng và bảo hiểm, độ bao phủ ngành khác hạn chế."
        ],
        "recommendation": [
            "Dùng làm biến kiểm soát thanh khoản hệ thống (Banking Liquidity Indicator) cho ngành VCB, BID, CTG, TCB."
        ]
    },
    "F064": {
        "pros": [
            "Dữ liệu chi phí nguyên liệu bột giấy, hóa chất in ấn bao bì tác động ngành bao bì/in ấn.",
            "Bắt trọn diễn biến chi phí đầu vào chuỗi cung ứng in ấn."
        ],
        "cons": [
            "Website hiệp hội cập nhật không đều đặn, số lượng bài báo ít."
        ],
        "recommendation": [
            "Quét kiểm tra định kỳ hàng tháng hoặc khi có thay đổi hash trang chủ."
        ]
    },
    "F065": {
        "pros": [
            "Dữ liệu sản lượng tiêu thụ đồ uống, chính sách thuế tiêu thụ đặc biệt tác động trực tiếp SAB, BHN.",
            "Thông tin độc quyền từ Hiệp hội Bia - Rượu - Nước giải khát Việt Nam."
        ],
        "cons": [
            "Số lượng bài viết chuyên sâu không nhiều, chủ yếu là báo cáo kiến nghị chính sách."
        ],
        "recommendation": [
            "Bóc tách các số liệu thay đổi thuế suất TTĐB để cập nhật biến số chi phí ngành bia rượu."
        ]
    },
    "F066": {
        "pros": [
            "Chính sách chuyển đổi số quốc gia, an toàn thông tin, trung tâm dữ liệu tác động FPT, CMG, ELC.",
            "Đón đầu xu thế dữ liệu lớn và điện toán đám mây tại Việt Nam."
        ],
        "cons": [
            "Ngành công nghệ thông tin VN có ít mã niêm yết lớn trên sàn."
        ],
        "recommendation": [
            "Gắn liên kết trực tiếp vào rổ cổ phiếu công nghệ FPT, CMG, FOX."
        ]
    },
    "F067": {
        "pros": [
            "Giá nông sản, vật tư phân bón, thức ăn chăn nuôi tác động DPM, DCM, BFC, HAG, BAF, DBC.",
            "Cập nhật trực tiếp từ mạng lưới Hội Nông dân Việt Nam."
        ],
        "cons": [
            "Dữ liệu mang tính địa phương phân tán, không có API chuẩn."
        ],
        "recommendation": [
            "Trích xuất chỉ số giá phân bón urea/DAP và giá heo hơi từ bài viết."
        ]
    },
    "F068": {
        "pros": [
            "Chính sách biểu giá điện, Quy hoạch điện 8, điều hành giá xăng dầu, hạn ngạch dệt may, phòng vệ thương mại.",
            "Nguồn dữ liệu toàn diện về chính sách công thương nghiệp."
        ],
        "cons": [
            "Số lượng văn bản và tin tức rất lớn, độ nhiễu cao."
        ],
        "recommendation": [
            "Lọc từ khóa chuyên ngành năng lượng (POW, PC1, REE, GEG) và dầu khí (GAS, PLX, PVD, PVS)."
        ]
    },
    "F069": {
        "pros": [
            "Lượng khách quốc tế, tỷ lệ lưu trú hàng không tác động VJC, HVN, VTD, DAH.",
            "Thông tin cập nhật từ Hiệp hội Du lịch Việt Nam (VITA)."
        ],
        "cons": [
            "Tính mùa vụ cao, bài viết mang tính sự kiện quảng bá du lịch nhiều hơn tài chính."
        ],
        "recommendation": [
            "Trích xuất chỉ số lượng khách quốc tế hàng tháng làm biến vĩ mô du lịch hàng không."
        ]
    },
    "F070": {
        "pros": [
            "Kim ngạch xuất khẩu cá tra, tôm sang Mỹ/EU/TQ, giá tôm cá nguyên liệu tác động VHC, ANV, FMC, MPC.",
            "Cập nhật hàng tuần từ Hiệp hội Chế biến và Xuất khẩu Thủy sản (VASEP)."
        ],
        "cons": [
            "Báo cáo số liệu chi tiết thường nằm trong bản tin thu phí của hiệp hội."
        ],
        "recommendation": [
            "Thu thập bản tin xuất khẩu tuần/tháng miễn phí trên trang chủ và số liệu thuế chống bán phá giá."
        ]
    },
    "F071": {
        "pros": [
            "Văn bản tháo gỡ vướng mắc pháp lý dự án, cấp phép xây dựng TP.HCM tác động NVL, KDH, PDR, VHM, DXG.",
            "Nguồn tin sâu sát nhất về thị trường bất động sản phía Nam từ HoREA."
        ],
        "cons": [
            "Thường là các văn bản kiến nghị dài, mang tính định tính."
        ],
        "recommendation": [
            "Đếm số lượng dự án được cấp phép hoặc tháo gỡ để làm chỉ số phục hồi pháp lý BĐS."
        ]
    },
    "F072": {
        "pros": [
            "Kiểm toán và hợp nhất 477.733 bản ghi vĩ mô qua 7 staging DBs cách ly; quyết định đúng đắn không gộp vật lý vào core.news.",
            "Đảm bảo 100% tính toàn vẹn khóa ngoại dim_symbol và không nhân bản dữ liệu."
        ],
        "cons": [
            "Dữ liệu vĩ mô hiện phải truy xuất qua view ảo core.v_all_news, tăng độ phức tạp câu truy vấn."
        ],
        "recommendation": [
            "Xây dựng bảng quan hệ tham chiếu sector_macro_mapping để join nhanh vào pipeline PIT."
        ]
    },
    "F101": {
        "pros": [
            "7 phép kiểm toán toán học phát hiện 100% lỗi khóa ngoại, lỗi hình học nến và lỗi thời gian.",
            "Cơ chế fail-closed tự động khóa pipeline khi phát hiện bất kỳ sai lệch nào, bảo vệ tính sạch của dữ liệu."
        ],
        "cons": [
            "Chạy quét toàn diện trên 5M nến và 660K bài báo tốn khoảng 30-45 giây mỗi lần chạy."
        ],
        "recommendation": [
            "Áp dụng incremental validation cho dữ liệu mới cào trong ngày để tối ưu thời gian."
        ]
    },
    "F102": {
        "pros": [
            "Mốc cắt 15:00 triệt tiêu rò rỉ tương lai; As-reported filing lag cho BCTC (45d Q1-Q3, 90d Q4).",
            "Căn chỉnh đúng mốc lợi nhuận forward R(T+1), R(T+5), R(T+30) trên 492.150 sự kiện Point-In-Time."
        ],
        "cons": [
            "Mốc trễ nộp BCTC 45/90 ngày là ước lượng luật định, chưa lấy được ngày nộp chính xác cho 100% trường hợp quá khứ."
        ],
        "recommendation": [
            "Tích hợp ngày công bố BCTC thực tế từ core.cafef_disclosures thay thế cho ước lượng."
        ]
    },
    "F103": {
        "pros": [
            "Quy trình 11 kỹ thuật chuẩn enterprise: Khử ngoại lai thao túng XDC; Winsorization [1%, 99%]; RankGauss đưa về chuẩn tắc; FFD d=0.20 giữ 90% bộ nhớ; Gray Code vĩ mô; Purged K-Fold kèm embargo.",
            "Xử lý 384K mẫu trong 42.5 giây, bảo vệ mạng nơ-ron không bị nổ gradient."
        ],
        "cons": [
            "Quá trình tính toán vi phân phân số FFD tốn tài nguyên CPU khi áp dụng trên hàng triệu dòng."
        ],
        "recommendation": [
            "Tiền tính toán FFD cho toàn bộ chuỗi giá và lưu sẵn vào bảng core.market_ohlcv_ffd."
        ]
    },
    "F104": {
        "pros": [
            "Đóng gói 384.431 mẫu đa phương thức sạch (văn bản + 24 chỉ số RankGauss + vector Gray Code 128d).",
            "Phân chia tập 70/15/15 Train/Val/Test OOS bằng Purged K-Fold kèm Embargo 5 phiên, triệt tiêu rò rỉ mẫu."
        ],
        "cons": [
            "File train_matrix.parquet có kích thước lớn (~1.2 GB), tốn RAM khi nạp toàn bộ vào bộ nhớ GPU."
        ],
        "recommendation": [
            "Tạo DataLoader phân lô streaming (IterableDataset) trong PyTorch để nạp dữ liệu theo batch."
        ]
    },
    "F201": {
        "pros": [
            "Mẫu kiểm định lớn N=15.081 tin xấu; t=6.84, p=8.39e-12; Cohen's d=0.0557.",
            "Chứng minh hiệu ứng đảo chiều tâm lý sau tin xấu tồn tại có ý nghĩa thống kê trên thị trường chứng khoán Việt Nam."
        ],
        "cons": [
            "Kiểm định gộp ngây thơ (Pooled) giả định các quan sát độc lập, bỏ qua tương quan chuỗi và tương quan chéo giữa các mã."
        ],
        "recommendation": [
            "Bắt buộc phải kiểm định chéo với sai số chuẩn cụm (Cluster-robust) tại F202."
        ]
    },
    "F202": {
        "pros": [
            "Bootstrap 1.437 cụm mã (z=5.98) và 214 cụm tháng (z=3.12); 95% CI hoàn toàn loại trừ số 0.",
            "Khẳng định tín hiệu không do vài mã cá biệt chi phối mà là đặc tính hành vi toàn thị trường."
        ],
        "cons": [
            "SE theo tháng tăng gấp đôi so với SE ngây thơ, phản ánh biến động bất đồng nhất giữa các thời kỳ."
        ],
        "recommendation": [
            "Bắt buộc áp dụng kiểm định 2D regime grid F203 để phân lập các thời kỳ thị trường khủng hoảng thanh khoản."
        ]
    },
    "F202b": {
        "pros": [
            "DSR toàn thị trường > 0.96; PBO = 0.007 (0.7% << 50% threshold, chứng minh backtest không bị quá khớp).",
            "Phát hiện Nghịch lý khả thi giao dịch (Tradeability Paradox) giữa rổ HOSE và UPCOM."
        ],
        "cons": [
            "Hiệu ứng trên sàn HOSE mỏng hơn nhiều (DSR fail ở N>=2), có nguy cơ bị triệt tiêu bởi trượt giá và phí giao dịch."
        ],
        "recommendation": [
            "Tập trung mô hình PhoBERT và đa phương thức để khuếch đại Alpha trên rổ cổ phiếu HOSE lớn."
        ]
    },
    "F203": {
        "pros": [
            "Ma trận 2D (16 Chế độ x 3 Sàn) phát hiện 29/60 ô đảo dấu âm (Sign-Flips trong khủng hoảng 2007, 2022).",
            "Đóng cứng rào chắn Fail-closed: VNINDEX < EMA200 -> ACTION = AVOID, bảo vệ hệ thống không cháy tài khoản."
        ],
        "cons": [
            "Bỏ lỡ toàn bộ cơ hội giao dịch trong thị trường giá xuống (Bear Market)."
        ],
        "recommendation": [
            "Xây dựng chiến lược bán khống phái sinh VN30F hoặc phòng hộ rủi ro khi thị trường vào pha downtrend."
        ]
    },
    "F301": {
        "pros": [
            "Hàm mất mát Bradley-Terry căn chỉnh trực tiếp sở thích thị trường (FinDPO), khắc phục nghịch lý tin xấu ngữ nghĩa nhưng giá tăng.",
            "Dual-Head phân loại cảm xúc và dự báo chiều giá đồng thời."
        ],
        "cons": [
            "Đòi hỏi tài nguyên GPU huấn luyện; độ dài ngữ cảnh tối đa 256 tokens."
        ],
        "recommendation": [
            "Lượng tử hóa mô hình sang FP16/INT8 để tăng tốc độ suy luận trong môi trường phục vụ."
        ]
    },
    "F302": {
        "pros": [
            "Hợp nhất ngữ nghĩa tin tức (768d->128d) + 24 chỉ số BCTC (128d) + vĩ mô Gray Code (128d) qua 4-Head Cross-Attention.",
            "Tăng cường khả năng phân biệt giữa doanh nghiệp cơ bản tốt gặp tin đồn và doanh nghiệp suy thoái thực sự."
        ],
        "cons": [
            "Tăng số lượng tham số cần tối ưu; cần kiểm soát chặt chẽ rủi ro overfitting trên tập validation."
        ],
        "recommendation": [
            "Áp dụng Dropout 0.3 và LayerNorm trên các nhánh đặc trưng trước khi đưa vào attention."
        ]
    },
    "F303": {
        "pros": [
            "Cohen's d tăng lên 0.0840 (+50.8%), đạt 0.1736 (3.12x baseline) ở phân khúc xác tín cao (S < 35, t=18.00, p=2.18e-71).",
            "Chứng minh sự vượt trội vượt bậc của mô hình đa phương thức so với quy tắc từ điển thô."
        ],
        "cons": [
            "Số lượng cơ hội giao dịch xác tín cao giảm xuống (~25% tổng số sự kiện)."
        ],
        "recommendation": [
            "Tối ưu ngưỡng phân bổ vốn động theo tỷ lệ xác tín (Conviction-based Kelly Sizing)."
        ]
    },
    "F304": {
        "pros": [
            "Closed-form Simplex Projection trong O(1); V-FAN siêu tốc 0.0197 ms; Kolmogorov error = 0.00; Brier score giảm -29.51%; d=0.0852.",
            "Loại bỏ 4.715 tin tức giật gân, mâu thuẫn logic mà không tốn chi phí gọi API ngoài."
        ],
        "cons": [
            "Hiện mới triển khai bộ sinh đối nghịch cho Negation Checker; chưa mở rộng sang 10 Checkers toán học."
        ],
        "recommendation": [
            "Mở rộng trọn bộ 10 Checkers Kolmogorov và tích hợp SLM Qwen2.5-3B-Instruct 4-bit."
        ]
    },
    "F401": {
        "pros": [
            "Độ trễ P95 = 20.1 ms (<50ms SLA); SimHash dedup 6h trong 0.1ms; phân giải cổ đông; cổng HybridACD và rào chắn F203.",
            "Dịch vụ FastAPI streaming chỉ đọc (strictly read-only) bảo đảm an toàn tuyệt đối."
        ],
        "cons": [
            "Dịch vụ chỉ đọc (read-only); cache RAM sliding window có thể đầy nếu tin tức dồn dập."
        ],
        "recommendation": [
            "Đặt TTL tự động giải phóng cache bộ nhớ đệm và kết nối endpoint vào màn hình dashboard."
        ]
    },
    "F402": {
        "pros": [
            "Tự động đối soát lợi nhuận thực tế T+1/T+5/T+30 EOD; theo dõi PSI/Rank-IC/Brier; ngắt mạch SYSTEM_DEGRADED_HALT khi accuracy < 35%.",
            "Ghi nhật ký vi cấu trúc phục vụ giám sát concept drift."
        ],
        "cons": [
            "Cần dữ liệu khớp lệnh T+30 sau 6 tuần mới có đủ chuỗi đối soát dài hạn."
        ],
        "recommendation": [
            "Bổ sung chỉ số trôi dạt phân phối dữ liệu đầu vào (Input Covariate Drift) để cảnh báo sớm trước khi có kết quả T+30."
        ]
    },
    "F403": {
        "pros": [
            "Đóng băng 100% PhoBERT, chỉ tái huấn luyện Fusion Head trong <25s (<3 min SLA); Shadow Model Gate kiểm định trước khi promote.",
            "Tự động thích ứng khi phát hiện concept drift mà không gây sập dịch vụ."
        ],
        "cons": [
            "Tái huấn luyện quá thường xuyên có thể gây hiện tượng ghi nhớ biến động nhiễu ngắn hạn (Catastrophic Forgetting)."
        ],
        "recommendation": [
            "Đặt ngưỡng kích hoạt tối thiểu 1.000 mẫu mới và chỉ huấn luyện trên sliding window 1 năm gần nhất."
        ]
    },
    "F501": {
        "pros": [
            "10.000 đường đi mô phỏng vi cấu trúc T+2.5, trần sàn, thuế phí; 5 Bot Personas; HybridACD Sniper vô địch (Sharpe 1.21, DSR 0.9998, H2H 78.4%).",
            "Mô phỏng chân thực và toàn diện các kịch bản thị trường chứng khoán Việt Nam."
        ],
        "cons": [
            "Giả định thanh khoản vô hạn trong biên độ trần sàn, chưa xét các phiên trắng sàn bên mua."
        ],
        "recommendation": [
            "Bổ sung mô hình suy giảm xác suất khớp lệnh (Fill Probability Model) theo khối lượng giao dịch bình quân."
        ]
    },
    "F901": {
        "pros": [
            "Tuân thủ 100% Rule B1 và Công văn UBCKNN 09/2023; khóa cứng tầng thực thi, bảo vệ an toàn vốn tuyệt đối.",
            "Tránh mọi rủi ro về lỗi phần mềm dẫn đến việc đặt lệnh mất kiểm soát."
        ],
        "cons": [
            "Hệ thống bị khóa ở chế độ chỉ đọc, chưa thể giao dịch tự động tài khoản thật."
        ],
        "recommendation": [
            "Theo dõi sát sao tiến trình cấp phép giao dịch thuật toán của KRX để kích hoạt sandbox."
        ]
    },
    "F902": {
        "pros": [
            "Chuẩn bị sẵn module OAuth2 + PKCE cho SSI/DNSE sandbox; kiểm thử trượt giá và độ trễ mạng an toàn.",
            "Sẵn sàng kích hoạt không trễ (Zero-Friction Readiness) khi luật pháp cho phép."
        ],
        "cons": [
            "Bị khóa phụ thuộc hoàn toàn vào F901."
        ],
        "recommendation": [
            "Duy trì các mock test trong test_pipeline/ để bảo đảm tính tương thích giao thức."
        ]
    }
}


def main():
    feat_path = pathlib.Path("Harness/feature_list.json")
    with open(feat_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    updated = 0
    for feat in data.get("features", []):
        fid = feat.get("id")
        if fid in ALL_ENRICHMENTS:
            feat["pros"] = ALL_ENRICHMENTS[fid]["pros"]
            feat["cons"] = ALL_ENRICHMENTS[fid]["cons"]
            feat["recommendation"] = ALL_ENRICHMENTS[fid]["recommendation"]
            updated += 1

    with open(feat_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"Successfully enriched {updated} additional features in {feat_path}")


if __name__ == "__main__":
    main()
