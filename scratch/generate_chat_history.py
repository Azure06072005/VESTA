import json
import pathlib
import datetime

# Load turns summary
with open("d:/VESTA/scratch/turns_summary.json", "r", encoding="utf-8") as f:
    turns = json.load(f)

md_lines = []
md_lines.append("# VESTA: NHẬT KÝ HỘI THOẠI & TIẾN ĐỘ TOÀN DIỆN (COMPREHENSIVE CHAT HISTORY)")
md_lines.append(f"> **Tệp lưu trữ:** `CHAT_HISTORY.md`  ")
md_lines.append(f"> **Mã phiên làm việc (Conversation ID):** `d8334d76-6f02-4079-adcd-a6b0aac346f2`  ")
md_lines.append(f"> **Cập nhật lần cuối:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (T-0: 09/10/2026)  ")
md_lines.append(f"> **Quy chuẩn ghi nhận:** Tự động lưu trữ chi tiết toàn bộ câu hỏi (User Prompt), hành động kỹ thuật (Engineering Actions), và câu trả lời (Agent Response) trong toàn bộ phiên làm việc.")
md_lines.append("\n---\n")

md_lines.append("## MỤC LỤC TỔNG HỢP (TABLE OF CONTENTS)")
turn_titles = [
    "Turn 1: Khảo sát, phân tích toàn diện mã nguồn, 3 CSDL ban đầu, Harness & Báo cáo",
    "Turn 2: Tự do hóa tư duy suy luận mô hình SLM, Odd-lot 10M VNĐ & RAG Studio",
    "Turn 3: Thiết lập CSDL Admin, tự động cào khi khởi động & Hợp nhất Feedback vào Dashboard",
    "Turn 4: Xử lý nghẽn khóa tệp DuckDB, chuyển đổi bộ đệm và sửa hiển thị index_code",
    "Turn 5: Xây dựng Admin Model Test Page: Kiểm định đối đầu BOT-N1 vs BOT-A108 (F104 Embargo)",
    "Turn 6: Tái cơ cấu quy trình F001-F099, thay thế hoàn toàn Vnstock API bằng nguồn độc lập",
    "Turn 7: Tối ưu đa luồng cào song song, tách 3 CSDL thành 5 CSDL Nhiệm vụ Chuyên biệt (F073-F076)",
    "Turn 8: Thiết lập SLA Yêu cầu dữ liệu (Min 2000, Max istoday), loại bỏ Snapshot, cập nhật Progress Report",
    "Turn 9: Hai tầng Hybrid Ensemble, đại tu khử trùng lặp 956K hàng (vấn đề fetched_at), Gate chất lượng",
    "Turn 10: Đào sâu CSDL OHLCV: Cào bù nến 1m (23.1M nến) & Inception Crawl toàn bộ Phái sinh, ETF, CW",
    "Turn 11: Đào sâu đồng bộ 4 CSDL còn lại (News 1.15M tin, Market Index 4.85M flow, Fundamentals, Events)",
    "Turn 12: Cập nhật giao diện Web Console: Bảng điện T-0, Fear & Greed 36.05, Phân lớp Đa Tài sản",
    "Turn 13: Trừu tượng hóa & Tự động ghi nhật ký hội thoại toàn diện vào CHAT_HISTORY.md"
]

for idx, title in enumerate(turn_titles[:len(turns)]):
    md_lines.append(f"- [{title}](#turn-{idx+1})")

md_lines.append("\n---\n")

# Executive Summary
md_lines.append("## TỔNG KẾT CÁC CỘT MỐC CÔNG VIỆC TRỌNG TÂM ĐÃ HOÀN THÀNH (EXECUTIVE SYNTHESIS)")
md_lines.append("""
1. **Kiến Trúc 5 Cơ Sở Dữ Liệu Nhiệm Vụ Chuyên Biệt (5 Mission Databases):**
   - Đã khai tử `vesta_snapshot.duckdb` để giải quyết triệt để vấn đề xung đột khóa tệp (File Locks) trên Windows.
   - Thiết lập cấu trúc 5 CSDL chuyên biệt: `vesta_ohlcv.duckdb`, `vesta_market_index.duckdb`, `vesta_news.duckdb`, `vesta_fundamentals.duckdb`, `vesta_events.duckdb`.
   - Toàn bộ 5 CSDL được nhân bản đồng bộ sang thư mục `db/admin/*.duckdb` phục vụ chế độ Resilient Read-Only.

2. **Dữ Liệu Đạt Chuẩn Toàn Diện T-0 (2026-10-09) & Dải Lịch Sử Sâu Đến Năm 2000:**
   - **OHLCV 1D:** 4,282,573 nến ngày (2000-07-28 -> 2026-10-09) trên toàn bộ cổ phiếu.
   - **OHLCV 1M:** 23,121,653 nến 1 phút cao tần (2023-09-11 -> 2026-10-09 14:59:00). Đã cào bù hoàn tất khoảng trống 3 tuần bị thiếu (+279,395 nến).
   - **Phái sinh VN30F (F073):** 9,152 nến từ ngày khai sinh thị trường phái sinh Việt Nam (2017-08-10 -> 2026-10-09).
   - **Chứng quyền CW (F074):** 27,087 nến trên 339 mã CW niêm yết.
   - **Quỹ ETF (F075):** 26,007 nến trên toàn bộ 24 quỹ ETF (2014-10-06 -> 2026-10-09).
   - **Dòng tiền Khối ngoại (F054):** 4,851,518 dòng (2001-04-02 -> 2026-10-09). Đã cào bù 20 phiên gần nhất (+11,798 dòng).
   - **Tâm lý & Độ rộng TT (F007b):** 18,785 bản ghi Fear & Greed và 2,250 bản ghi độ rộng MA20/MA50 đến T-0.
   - **Tin tức tài chính (F003/F004):** 1,152,213 bài báo CafeF & Vietstock (2005 -> 2026-10-09 17:53:34).
   - **BCTC & Thuyết minh (F005):** 7,358,616 bản ghi thuyết minh chi tiết và 71,842 BCTC chuẩn hóa (2000 -> 2026-Q2).
   - **Sự kiện doanh nghiệp (F006):** 37,488 sự kiện cổ tức và ĐHĐCĐ kéo dài đến 21/10/2026.

3. **Khử Hoàn Toàn 956,211 Hàng Trùng Lặp & Xử Lý Cột `fetched_at`:**
   - Đã phát hiện và làm sạch lỗi nhân bản dữ liệu do cột `fetched_at` mang timestamp khác nhau qua các lần cào.
   - Triển khai cơ chế sáp nhập nguyên tử 2 bước (2-step ACID Delete + Insert) cho mọi bảng DuckDB không có Primary Key tự nhiên.

4. **Độc Lập Nguồn Dữ Liệu & Pipeline Cào Song Song Siêu Tốc:**
   - Thay thế toàn bộ dependency phụ thuộc vào gói `vnstock` bằng các API trực tiếp: Vietcap Bulk API, CafeF Raw Stream, VNDirect, TCBS, SSI iBoard.
   - Tối ưu hóa đa luồng (12-16 workers) giảm thời gian cào từ 4-5 tiếng xuống còn **dưới 35 giây** cho các đợt cập nhật nhanh.

5. **Nâng Cấp Giao Diện Web Console Hoàn Chỉnh (Port 8899):**
   - **Bảng điện T-0:** Hiển thị điểm số Fear & Greed (36.05 - Thận trọng), thanh khoản 12,537.9 Tỷ VNĐ, Khối ngoại bán ròng -406.3 Tỷ VNĐ.
   - **Phân lớp Đa Tài sản:** Bổ sung thanh chuyển đổi Cổ phiếu Heatmap, Phái sinh VN30F, Quỹ ETF, Chứng quyền CW; liên kết trực tiếp biểu đồ nến kỹ thuật.
   - **Admin Model Test Page:** Bảng điều khiển kiểm định backtest độc lập giữa BOT-N1 (Rule-based) và BOT-A108 (AI Twin) trên bộ dữ liệu F104 Embargo.
   - **Overview Page:** Bảng theo dõi thời gian thực dung lượng và số bản ghi của 5 cơ sở dữ liệu Lakehouse.
""")

md_lines.append("\n---\n")
md_lines.append("## CHI TIẾT LỊCH SỬ HỘI THOẠI TỪNG BƯỚC (TURN-BY-TURN TRANSCRIPT)")

for idx, t in enumerate(turns):
    turn_num = t["turn"]
    title = turn_titles[idx] if idx < len(turn_titles) else f"Turn {turn_num}"
    md_lines.append(f"\n### <a id='turn-{turn_num}'></a> {title}")
    md_lines.append(f"**Thời điểm ghi nhận:** Phiên làm việc VESTA Session  ")
    
    # User Prompt
    md_lines.append("\n#### 👤 Yêu Cầu Của Người Dùng (User Prompt):")
    md_lines.append("```text")
    md_lines.append(t["user_prompt"])
    md_lines.append("```")
    
    # Key Actions
    if t.get("key_actions"):
        md_lines.append("\n#### 🛠️ Các Hành Động Kỹ Thuật Đã Triển Khai (Engineering Actions):")
        # filter and deduplicate actions
        seen = set()
        clean_actions = []
        for a in t["key_actions"]:
            if a not in seen:
                seen.add(a)
                clean_actions.append(a)
        for ca in clean_actions[:15]:
            md_lines.append(f"- {ca}")
        if len(clean_actions) > 15:
            md_lines.append(f"- *(Và {len(clean_actions) - 15} thao tác kiểm tra/chỉnh sửa bổ sung khác...)*")
            
    # Assistant Response
    md_lines.append("\n#### 🤖 Phản Hồi & Nghiệm Thu Của Trợ Lý (Assistant Response):")
    resp = t.get("final_response", "")
    if resp:
        md_lines.append(resp)
    else:
        md_lines.append("*(Tiến trình đang được tiếp tục xử lý trong lượt hội thoại tiếp theo)*")
        
    md_lines.append("\n---\n")

out_file = pathlib.Path("d:/VESTA/CHAT_HISTORY.md")
with open(out_file, "w", encoding="utf-8") as f:
    f.write("\n".join(md_lines))

print(f"Successfully generated {out_file} (Size: {out_file.stat().st_size} bytes)")
