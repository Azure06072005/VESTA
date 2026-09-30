"""Unit tests cho chính sách cấm cào SBV và bảo vệ WAF (tests/test_sbv_crawler.py).

Tuân thủ nghiêm ngặt Ethical Crawling Guardrails:
1. Xác nhận sbv.gov.vn nằm trong danh mục cấm vĩnh viễn (WAF Bot Rejection).
2. Kiểm tra ném ngoại lệ PermissionError khi cố gắng cào sbv.gov.vn.
3. Xác nhận các nguồn thay thế hợp pháp (Thời Báo Ngân Hàng, Báo Chính Phủ) luôn hợp lệ.
"""

from __future__ import annotations

from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from crawlers.crawl_policy import (
    is_url_allowed,
    is_source_allowed,
    check_compliance_or_raise,
    FORBIDDEN_DENYLIST_DOMAINS,
    FORBIDDEN_SOURCE_IDENTIFIERS,
)


def test_sbv_domain_in_denylist():
    """Kiểm tra domain sbv.gov.vn có trong danh sách cấm vĩnh viễn."""
    assert "sbv.gov.vn" in FORBIDDEN_DENYLIST_DOMAINS
    assert "www.sbv.gov.vn" in FORBIDDEN_DENYLIST_DOMAINS


def test_sbv_source_identifier_forbidden():
    """Kiểm tra mã định danh nguồn SBV bị cấm."""
    assert "sbv" in FORBIDDEN_SOURCE_IDENTIFIERS
    assert "sbv_policy" in FORBIDDEN_SOURCE_IDENTIFIERS
    assert not is_source_allowed("sbv")
    assert not is_source_allowed("sbv_policy")


def test_is_url_allowed_rejects_sbv():
    """Kiểm tra is_url_allowed từ chối mọi URL từ sbv.gov.vn."""
    urls = [
        "https://sbv.gov.vn/vi/tin-tuc-su-kien",
        "https://sbv.gov.vn/vi/w/408.000-ty-dong-san-sang-tiep-suc",
        "http://www.sbv.gov.vn/portal/faces/index",
    ]
    for url in urls:
        allowed, reason = is_url_allowed(url)
        assert not allowed
        assert "CẤM VĨNH VIỄN" in reason


def test_check_compliance_or_raise_sbv():
    """Kiểm tra hàm check_compliance_or_raise ném PermissionError khi gặp SBV."""
    with pytest.raises(PermissionError) as exc_info:
        check_compliance_or_raise("https://sbv.gov.vn/vi/tin-tuc")
    assert "CRAWL POLICY VIOLATION" in str(exc_info.value)

    with pytest.raises(PermissionError) as exc_info_src:
        check_compliance_or_raise("sbv")
    assert "CRAWL POLICY VIOLATION" in str(exc_info_src.value)


def test_legitimate_sbv_substitutes_allowed():
    """Xác nhận các kênh thay thế hợp pháp cho chính sách tiền tệ SBV luôn được phép."""
    # 1. Thời Báo Ngân Hàng (Cơ quan ngôn luận của Ngân hàng Nhà nước)
    assert is_source_allowed("thoibaonganhang")
    tbnh_allowed, _ = is_url_allowed("https://thoibaonganhang.vn/chinh-sach-tien-te-1234.html")
    assert tbnh_allowed

    # 2. Báo Chính Phủ
    assert is_source_allowed("baochinhphu")
    bcp_allowed, _ = is_url_allowed("https://baochinhphu.vn/nghi-quyet-chinh-phu.htm")
    assert bcp_allowed
