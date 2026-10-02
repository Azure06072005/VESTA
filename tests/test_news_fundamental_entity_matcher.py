"""tests/test_news_fundamental_entity_matcher.py

Bộ kiểm thử đơn vị cho phân hệ Ánh xạ Thực thể Tin tức sang Dữ liệu Cơ bản (F105).
(Unit tests for News-to-Fundamental Entity Resolution & Financial Relevance Gate).
"""
import sys
from pathlib import Path
import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pipeline.news_fundamental_entity_matcher import (
    FinancialRelevanceClassifier,
    FundamentalEntityRegistry,
    ensure_entity_tables,
    normalize_vietnamese_key,
)


def test_normalize_vietnamese_key():
    assert normalize_vietnamese_key("  Phạm Nhật Vượng!!  ") == "phạm nhật vượng"
    assert normalize_vietnamese_key("CTCP Tập đoàn FPT") == "ctcp tập đoàn fpt"
    assert normalize_vietnamese_key("") == ""
    assert normalize_vietnamese_key(None) == ""


def test_financial_relevance_classifier_noise():
    classifier = FinancialRelevanceClassifier()

    # Tin tức Showbiz / Scandal
    cat, is_rel, score = classifier.classify_article(
        headline="Showbiz rúng động trước scandal tình ái của diễn viên nổi tiếng",
        body="Nhiều thông tin cho thấy vụ hẹn hò đã gây xôn xao dư luận.",
    )
    assert cat == "IRRELEVANT_NOISE"
    assert is_rel is False
    assert score < 0.2

    # Tin tức tai nạn / án mạng
    cat, is_rel, score = classifier.classify_article(
        headline="Va chạm giao thông liên hoàn khiến 2 người tử vong tại chỗ",
        body="Cơ quan công an đang điều tra hiện trường vụ tai nạn.",
    )
    assert cat == "IRRELEVANT_NOISE"
    assert is_rel is False


def test_financial_relevance_classifier_macro_finance():
    classifier = FinancialRelevanceClassifier()

    # Tin vĩ mô kinh tế & ngân hàng
    cat, is_rel, score = classifier.classify_article(
        headline="Ngân hàng Nhà nước giảm lãi suất điều hành hỗ trợ tăng trưởng kinh tế",
        body="Tín dụng dự kiến mở rộng mạnh trong quý 4 nhằm thúc đẩy tăng trưởng GDP.",
    )
    assert cat == "FINANCIAL_MACRO"
    assert is_rel is True
    assert score >= 0.85


def test_financial_relevance_classifier_entity_priority():
    classifier = FinancialRelevanceClassifier()

    # Ngay cả khi có từ ngữ xã hội, nếu đã gắn với thực thể doanh nghiệp -> Luôn giữ lại
    cat, is_rel, score = classifier.classify_article(
        headline="Vingroup trao giải thưởng khoa học công nghệ toàn cầu",
        body="Chủ tịch Phạm Nhật Vượng tham dự lễ trao giải vinh danh các nhà khoa học.",
        has_matched_entity=True,
    )
    assert cat == "FINANCIAL_EQUITY"
    assert is_rel is True
    assert score == 1.0


def test_entity_registry_canonical_matching():
    registry = FundamentalEntityRegistry()
    registry.load_registry()

    # Khớp Chủ tịch Phạm Nhật Vượng trên tiêu đề
    matches = registry.match_entities_in_text(
        headline="Ông Phạm Nhật Vượng chia sẻ kế hoạch mở rộng thị trường xe điện toàn cầu",
        body="Tập đoàn kỳ vọng tăng trưởng sản lượng trong năm tới.",
        source_url="https://test.vn/article-1",
    )
    assert len(matches) > 0
    vic_matches = [m for m in matches if m.symbol == "VIC"]
    assert len(vic_matches) > 0
    assert vic_matches[0].entity_name == "Phạm Nhật Vượng"
    assert vic_matches[0].matched_location == "HEADLINE"
    assert vic_matches[0].confidence_score >= 0.95

    # Khớp Chủ tịch Trần Đình Long trên nội dung (Body)
    matches_body = registry.match_entities_in_text(
        headline="Ngành thép Việt Nam đón làn sóng phục hồi nhu cầu xây dựng",
        body="Tại buổi gặp mặt cổ đông, ông Trần Đình Long đánh giá biên lợi nhuận của doanh nghiệp sẽ khởi sắc.",
        source_url="https://test.vn/article-2",
    )
    hpg_matches = [m for m in matches_body if m.symbol == "HPG"]
    assert len(hpg_matches) > 0
    assert hpg_matches[0].entity_name == "Trần Đình Long"
    assert hpg_matches[0].matched_location == "BODY"
    assert hpg_matches[0].confidence_score == 0.85


def test_ensure_entity_tables_ddl():
    con = duckdb.connect(":memory:")
    ensure_entity_tables(con)

    # Kiểm tra tồn tại 2 bảng
    tables = [
        row[0]
        for row in con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='core';"
        ).fetchall()
    ]
    assert "news_entity_map" in tables
    assert "news_relevance_meta" in tables

    # Thử chèn bản ghi mẫu
    con.execute("""
        INSERT INTO core.news_entity_map 
        (source_url, symbol, entity_type, entity_name, entity_role, company_type, ownership_pct, confidence_score, matched_location)
        VALUES 
        ('https://cafef.vn/test', 'VIC', 'EXECUTIVE', 'Phạm Nhật Vượng', 'Chủ tịch HĐQT', 'Tập đoàn Đa ngành', 17.85, 0.95, 'HEADLINE');
    """)

    res = con.execute("SELECT symbol, entity_name, entity_role FROM core.news_entity_map").fetchone()
    assert res[0] == "VIC"
    assert res[1] == "Phạm Nhật Vượng"
    assert res[2] == "Chủ tịch HĐQT"
    con.close()


def test_brand_and_ticker_disambiguation():
    """Kiểm tra nhận diện thương hiệu 1 từ (Vinamilk, Vietcombank, Techcombank, Vinhomes) và Ticker có ngữ cảnh."""
    registry = FundamentalEntityRegistry()
    registry.load_registry()

    # 1. Thương hiệu 1 từ
    matches_vnm = registry.match_entities_in_text(
        headline="Vinamilk công bố chiến lược phát triển bền vững và mở rộng thị trường xuất khẩu",
        body="Doanh nghiệp đặt mục tiêu tăng trưởng doanh thu quý tới.",
    )
    assert any(m.symbol == "VNM" for m in matches_vnm)

    matches_vcb = registry.match_entities_in_text(
        headline="Vietcombank tiếp tục dẫn đầu lợi nhuận toàn ngành ngân hàng năm 2024",
    )
    assert any(m.symbol == "VCB" for m in matches_vcb)

    matches_tcb = registry.match_entities_in_text(
        headline="Techcombank tiên phong chuyển đổi số quy trình phê duyệt tín dụng",
    )
    assert any(m.symbol == "TCB" for m in matches_tcb)

    matches_vhm = registry.match_entities_in_text(
        headline="Vinhomes khởi công đại dự án khu đô thị sinh thái quy mô lớn",
    )
    assert any(m.symbol == "VHM" for m in matches_vhm)

    # 2. Ticker có ngữ cảnh
    matches_ticker = registry.match_entities_in_text(
        headline="Nhà đầu tư nước ngoài mua ròng đột biến cổ phiếu FPT và mã HPG trong phiên hôm nay",
    )
    symbols = {m.symbol for m in matches_ticker}
    assert "FPT" in symbols
    assert "HPG" in symbols


def test_cooccurrence_disambiguation_guard():
    """Kiểm tra cơ chế Co-occurrence Guard ngăn chặn va chạm trùng tên lãnh đạo (case FPT vs CLC)."""
    registry = FundamentalEntityRegistry()
    registry.load_registry()

    # Bài báo nói về FPT và Ba Huân, có ông Nguyễn Hoàng Minh (TGĐ FPT IS)
    # Tuyệt đối không được match sang CLC (Thuốc lá Cát Lợi) mà phải match sang FPT
    headline = "FPT và Ba Huân bắt tay thực hiện tầm nhìn chuyển đổi số doanh nghiệp nông nghiệp"
    body = (
        "Theo thoả thuận hợp tác, Tập đoàn FPT sẽ tư vấn chuyển đổi số toàn diện cho Ba Huân. "
        "Ông Nguyễn Hoàng Minh, Tổng Giám đốc FPT IS, đại diện ký kết thỏa thuận hợp tác cùng đối tác. "
        "Chủ tịch Trương Gia Bình nhấn mạnh tầm quan trọng của công nghệ trong nông nghiệp."
    )
    matches = registry.match_entities_in_text(headline, body, "https://test.vn/fpt-bahuan")

    symbols = {m.symbol for m in matches}
    assert "CLC" not in symbols, "Lỗi va chạm đa nghĩa: Bài báo FPT không được phép gán cho CLC!"
    assert "FPT" in symbols, "Phải nhận diện thành công mã FPT!"
