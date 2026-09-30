"""VESTA News Ingestion Policy & Ethical Crawling Guardrails.

Quy định và rào cản đạo đức bắt buộc trong thu thập tin tức:
1. PERMANENT DENYLIST: Dừng vĩnh viễn mọi hành vi gửi request tới các trang web cấm,
   chặn IP, paywall hoặc áp dụng WAF từ chối bot (SBV, Thư viện pháp luật, Luật Việt Nam...).
2. ETHICAL PACING BUFFER: Duy trì độ trễ tối thiểu (0.5s - 1.0s) giữa các request,
   tuyệt đối không gửi request dồn dập làm ảnh hưởng hạ tầng máy chủ nguồn.
3. DATE SANITIZATION: Triệt tiêu các lỗi trích xuất ngày tháng dị thường (< 1990 hoặc > năm hiện tại + 1).
4. CONTENT QUALITY GUARD: Lọc bỏ bài viết rác, bài viết không có tiêu đề hoặc bị cắt cụt.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger("crawl_policy")

# ==============================================================================
# 1. PERMANENT DENYLIST: DANH SÁCH TÊN MIỀN CẤM VĨNH VIỄN (FORBIDDEN SITES)
# ==============================================================================
# Các trang web có chính sách nghiêm ngặt cấm cào tự động, áp dụng WAF, Paywall hoặc 403 Forbidden.
FORBIDDEN_DENYLIST_DOMAINS: set[str] = {
    # Cơ quan quản lý áp dụng WAF từ chối truy cập tự động
    "sbv.gov.vn",              # Ngân hàng Nhà nước VN (WAF 'The requested URL was rejected')
    "www.sbv.gov.vn",
    
    # Cổng thông tin pháp lý áp dụng Paywall & Anti-bot 403 Forbidden
    "thuvienphapluat.vn",      # Thư viện Pháp luật (403 Forbidden / Paywall anti-bot)
    "www.thuvienphapluat.vn",
    "luatvietnam.vn",          # Luật Việt Nam (403/429 Forbidden / CSRF token firewall)
    "www.luatvietnam.vn",
    
    # Các trang hiệp hội chặn bot, lỗi HTTP 429 Rate Limit hoặc máy chủ từ chối kết nối (403/503)
    "vnba.com.vn",             # Hiệp hội Ngân hàng (HTTP 429 Rate Limit liên tục)
    "vnba.org.vn",
    "www.vnba.com.vn",
    "vinasme.com.vn",          # Hiệp hội DN vừa và nhỏ (403/Timeout)
    "www.vinasme.com.vn",
    "vfaea.org.vn",            # Hiệp hội Thức ăn chăn nuôi (403/Timeout)
    "www.vfaea.org.vn",
    "vpsaspice.org.vn",        # Hiệp hội Hồ tiêu (403/Timeout)
    "www.vpsaspice.org.vn",
    "huba.vn",                 # Hiệp hội Doanh nghiệp TP.HCM (403/Timeout)
    "www.huba.vn",
    "vacod.com.vn",            # Hiệp hội VACOD (403/Timeout)
    "www.vacod.com.vn",
    "vama.org.vn",             # Hiệp hội Ô tô (403/Timeout)
    "www.vama.org.vn",
    "vafie.org.vn",            # Hiệp hội Đầu tư nước ngoài (403/Timeout)
    "www.vafie.org.vn",
    "viea.vn",                 # Hiệp hội Năng lượng sạch (403/Timeout)
    "www.viea.vn",
    "vecom.vn",                # Hiệp hội Thương mại điện tử (403/Timeout)
    "www.vecom.vn",
    "via.org.vn",              # Hiệp hội Internet (403/Timeout)
    "www.via.org.vn",
    "avnuc.vn",                # Hiệp hội ĐH-CĐ (403/Timeout)
    "www.avnuc.vn",
    "hhbvt.vn",                # Hiệp hội Bệnh viện tư nhân (403/Timeout)
    "www.hhbvt.vn",
    "vusta.vn",                # Liên hiệp các Hội KHKT (403/Timeout)
    "www.vusta.vn",
    # Các trang báo quốc tế hoặc kênh áp dụng Paywall / Bot Blocking gắt gao
    "reuters.com",             # Reuters (Strict Paywall / Cloudflare Bot Management)
    "www.reuters.com",
    "bloomberg.com",           # Bloomberg (Paywall / PerimeterX Bot Shield)
    "www.bloomberg.com",
    "wsj.com",                 # Wall Street Journal (Hard Paywall)
    "www.wsj.com",
    "vov.vn",                  # Đài Tiếng nói VN (403/Anti-Scrape WAF)
    "www.vov.vn",
    "baodautu.vn",             # Báo Đầu tư (403 Forbidden / Anti-bot WAF)
    "www.baodautu.vn",
    "tuoitre.vn",              # Báo Tuổi Trẻ (403 Forbidden / Anti-bot WAF)
    "www.tuoitre.vn",
    "tienphong.vn",            # Báo Tiền Phong (WAF / Anti-bot)
    "www.tienphong.vn",
    "nguoiquansat.vn",         # Người Quan Sát (403 Forbidden / Anti-bot)
    "www.nguoiquansat.vn",
    "tapchicongthuong.vn",     # Tạp chí Công Thương (WAF / Anti-bot)
    "www.tapchicongthuong.vn",
}

# Danh sách mã nguồn (source code identifier) bị cấm/loại bỏ vĩnh viễn
FORBIDDEN_SOURCE_IDENTIFIERS: set[str] = {
    "sbv", "sbv_policy", "thuvienphapluat", "luatvietnam", "vnba",
    "vinasme", "vfaea", "vpsaspice", "huba", "vacod", "vama",
    "vafie", "viea", "vecom", "via", "avnuc", "hhbvt", "vusta",
    "reuters", "bloomberg", "wsj", "vov",
    "baodautu", "tuoitre", "tienphong", "nguoiquansat", "tapchicongthuong", "tcct"
}


def is_source_allowed(source_name: str) -> bool:
    """Kiểm tra mã nguồn (identifier) có được phép cào hay không."""
    if not source_name:
        return False
    return source_name.lower().strip() not in FORBIDDEN_SOURCE_IDENTIFIERS


def is_url_allowed(url: str) -> tuple[bool, str]:
    """Kiểm tra URL có nằm trong danh mục cấm/chặn không.
    
    Trả về (is_allowed, reason).
    """
    if not url:
        return False, "URL rỗng"
        
    try:
        parsed = urlparse(url)
        domain = (parsed.netloc or "").lower().strip()
        # Loại bỏ port nếu có (vd domain.com:443)
        if ":" in domain:
            domain = domain.split(":")[0]
            
        for forbidden in FORBIDDEN_DENYLIST_DOMAINS:
            if domain == forbidden or domain.endswith("." + forbidden):
                return False, f"Tên miền '{domain}' nằm trong danh mục CẤM VĨNH VIỄN do chính sách WAF/Paywall/403"
                
        return True, "Hợp lệ"
    except Exception as e:
        return False, f"Lỗi phân tích URL: {e}"


def check_compliance_or_raise(target: str) -> None:
    """Ném ngoại lệ PermissionError nếu URL hoặc tên nguồn vi phạm chính sách cào."""
    if "://" in target:
        allowed, reason = is_url_allowed(target)
        if not allowed:
            raise PermissionError(f"[CRAWL POLICY VIOLATION] {reason} | URL: {target}")
    else:
        if not is_source_allowed(target):
            raise PermissionError(
                f"[CRAWL POLICY VIOLATION] Nguồn '{target}' đã bị gỡ bỏ vĩnh viễn theo chính sách cào đạo đức."
            )


def sanitize_published_date(
    pub_dt: dt.datetime | None, 
    fallback_dt: dt.datetime | None = None
) -> dt.datetime:
    """Làm sạch và bảo vệ tính hợp lệ của ngày xuất bản (Zero Date Anomalies).
    
    Quy tắc:
    - 1990-01-01 <= pub_dt <= now + 1 ngày (loại bỏ năm 1204, 1896, 2027...).
    - Nếu vi phạm, thay thế bằng fallback_dt (hoặc thời điểm hiện tại).
    """
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    fallback = fallback_dt or now
    if not pub_dt:
        return fallback

    # Bỏ timezone nếu có để so sánh đồng nhất
    clean_dt = pub_dt.replace(tzinfo=None) if hasattr(pub_dt, "tzinfo") and pub_dt.tzinfo else pub_dt
    min_valid = dt.datetime(1990, 1, 1, 0, 0, 0)
    max_valid = now + dt.timedelta(days=2)  # Cho phép chênh lệch múi giờ tối đa 2 ngày

    if clean_dt < min_valid or clean_dt > max_valid:
        logger.warning(
            f"[Date Sanitizer] Phát hiện ngày xuất bản bất thường: {clean_dt} -> Thay thế bằng: {fallback}"
        )
        return fallback

    return clean_dt


def validate_and_clean_article(record: dict[str, Any]) -> dict[str, Any] | None:
    """Kiểm tra tính toàn vẹn và làm sạch bản ghi bài viết trước khi nạp vào CSDL.
    
    - Kiểm tra URL có bị cấm không.
    - Kiểm tra tiêu đề.
    - Làm sạch ngày xuất bản.
    - Đảm bảo thân bài không bị rỗng (tự động fallback về headline + summary nếu thiếu).
    """
    url = record.get("source_url", "")
    allowed, reason = is_url_allowed(url)
    if not allowed:
        logger.warning(f"[Crawl Policy Reject] Bỏ qua bài viết: {reason} | URL: {url}")
        return None

    headline = str(record.get("headline", "")).strip()
    if not headline or len(headline) < 5:
        return None

    summary = str(record.get("summary", "")).strip()
    body = str(record.get("body", "")).strip()
    
    # Nếu thiếu thân bài, tự động fallback an toàn
    if not body:
        if summary and len(summary) > 20:
            body = summary
        else:
            body = headline

    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    raw_pub = record.get("published_at")
    clean_pub = sanitize_published_date(raw_pub, fallback_dt=now)

    cleaned_record = dict(record)
    cleaned_record["headline"] = headline
    cleaned_record["summary"] = summary if summary else headline
    cleaned_record["body"] = body
    cleaned_record["published_at"] = clean_pub
    cleaned_record["available_at"] = clean_pub
    cleaned_record["fetched_at"] = record.get("fetched_at") or now
    
    return cleaned_record
