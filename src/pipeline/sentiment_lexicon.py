"""Rule-based Vietnamese financial-news sentiment scorer (F201).

STATUS: STATED ASSUMPTION, NOT A SOURCED/VALIDATED LEXICON. Per B3
("numbers/claims need a source"), this is disclosed plainly: a web search
for an existing, publicly available Vietnamese *financial-domain* sentiment
lexicon (2026-08-25) found none with a citable, reproducible word list --
only general-purpose Vietnamese sentiment resources (e.g. Vietnamese
SentiWordNet extensions, UIT-VSMEC/UIT-VSFC emotion datasets) and
English-only finance lexicons (Loughran-McDonald). None of those are
finance-specific *and* Vietnamese *and* have a public word list that could
be imported and cited directly.

This lexicon is therefore a small, hand-built starter list of unambiguous
Vietnamese corporate-disclosure/financial-news vocabulary -- the kind of
words that appear literally in dividend announcements, earnings headlines,
and regulatory-action news (see F003/F004/F006 sample headlines already in
the repo, e.g. "phat hanh co phieu", "co tuc bang tien mat"). It is NOT
tuned or validated against a labeled Vietnamese financial-sentiment
dataset. Treat it exactly like F009's news-dedup threshold (0.75
similarity, 6-hour window): a stated assumption, cheap to ship, explicitly
flagged for revision once real labeled data or a proper VN finance lexicon
becomes available -- not a substitute for that validation.

Matching is on UNDECORATED (accent-stripped) lowercase substrings, because
headlines in this repo mix diacritics inconsistently (compare F003's
"FPT: Nghi quyet HDQT..." vs F004's diacritic-complete headlines) and a
strict accented match would silently miss real matches. Substring matching
over a short curated list is deliberately simple (Simplicity First, A2) --
no tokenization, no negation handling, no stemming. This WILL misclassify
some headlines (e.g. sarcasm, negated statements, multi-clause headlines
with mixed sentiment) -- that noise is expected and is exactly why F201's
statistical test needs a large-enough n to average it out, not proof this
lexicon is accurate at the individual-headline level.
"""
from __future__ import annotations

import re
import unicodedata

# =============================================================================
# 1. POSITIVE LEXICON TAXONOMY (Từ vựng Tích cực Đa tầng)
# =============================================================================

# 1.1. Báo cáo tài chính, Tăng trưởng & Mở rộng kinh doanh (Corporate & Fundamentals)
POSITIVE_CORPORATE_TERMS: tuple[str, ...] = (
    "tang truong",            # Tăng trưởng
    "loi nhuan tang",         # Lợi nhuận tăng
    "lai rong tang",          # Lãi ròng tăng
    "doanh thu tang",         # Doanh thu tăng
    "bien loi nhuan tang",    # Biên lợi nhuận tăng
    "vuot ke hoach",          # Vượt kế hoạch
    "ve dich som",            # Về đích sớm
    "hoan thanh ke hoach",    # Hoàn thành kế hoạch
    "dat ky luc",             # Đạt kỷ lục
    "ky luc",                 # Kỷ lục
    "hoi phuc",               # Hồi phục
    "phuc hoi manh",          # Phục hồi mạnh
    "mo rong",                # Mở rộng quy mô/thị phần
    "trung thau",             # Trúng thầu
    "thang dam phan",         # Thắng đàm phán
    "ky ket hop dong",        # Ký kết hợp đồng
    "hop tac chien luoc",     # Hợp tác chiến lược
    "co tuc",                 # Cổ tức
    "tra co tuc",             # Trả cổ tức
    "co tuc tien mat",        # Cổ tức tiền mặt
    "chia thuong",            # Chia thưởng cổ phiếu
    "tang von",               # Tăng vốn điều lệ
    "niem yet them",          # Niêm yết bổ sung
    "mua lai co phieu quy",   # Mua lại cổ phiếu quỹ
    "tai co cau thanh cong",  # Tái cơ cấu thành công
    "lai dot bien",           # Lãi đột biến
    "loi nhuan dot bien",     # Lợi nhuận đột biến
    "dong tien duong",        # Dòng tiền dương
    "nang room ngoai",        # Nâng tỷ lệ sở hữu nước ngoài (room ngoại)
    "doi tac ngoai",          # Đối tác ngoại rót vốn
    "tang truong an tuong",   # Tăng trưởng ấn tượng
    "tin hieu tich cuc",      # Tín hiệu tích cực
    "sang cua",               # Sáng cửa
    "khoi sac",               # Khởi sắc
    "kiem toan chap nhan toan phan", # Kiểm toán chấp nhận toàn phần
    "ra khoi dien canh bao",  # Được đưa ra khỏi diện cảnh báo
    "ra khoi dien kiem soat", # Được đưa ra khỏi diện kiểm soát
    "duoc cap phep tro lai",  # Được cấp phép giao dịch trở lại
    "duoc giao dich tro lai", # Được giao dịch bình thường trở lại
    "duoc cap margin",        # Được cấp ký quỹ margin trở lại
    "duoc giai toa phong toa",# Được giải tỏa phong tỏa tài sản
)

# 1.2. Hành vi thị trường, Dòng tiền & Khớp lệnh (Market Microstructure & Liquidity)
POSITIVE_MARKET_TERMS: tuple[str, ...] = (
    "but pha",                # Bứt phá
    "vuot dinh",              # Vượt đỉnh
    "vuot dinh thoi dai",     # Vượt đỉnh thời đại
    "pha dinh",               # Phá đỉnh
    "vuot can",               # Vượt cản kỹ thuật
    "pha can cheo",           # Phá cản chéo
    "dong tien lon",          # Dòng tiền lớn
    "dong tien thong minh",   # Dòng tiền thông minh (smart money)
    "dong tien ca map",       # Dòng tiền cá mập
    "dong tien dien",         # Dòng tiền điên
    "tien vao nhu nuoc",      # Tiền vào như nước
    "tien vao cuon cuon",     # Tiền vào cuồn cuộn
    "cau lenh ap dao",        # Lệnh cầu áp đảo
    "khoi ngoai mua rong",    # Khối ngoại mua ròng
    "khoi ngoai gom rong",    # Khối ngoại gom ròng
    "tu doanh mua rong",      # Tự doanh mua ròng
    "bung no thanh khoan",    # Bùng nổ thanh khoản
    "no von",                 # Nổ vol (khối lượng bùng nổ)
    "no vol",                 # Nổ vol
    "chay hang",              # Cháy hàng
    "trang ben ban",          # Trắng bên bán (dư mua trần)
    "tim lim",                # Tím lịm (tăng kịch trần)
    "tim tai",                # Tím tái (tăng kịch trần hàng loạt)
    "tang tran",              # Tăng trần
    "keo tran",               # Kéo trần
    "chat tran",              # Chất lệnh giá trần
    "chat tran hang trieu co",# Chất trần hàng triệu cổ
    "rut chan",               # Rút chân (nến đảo chiều tăng)
    "bat day thanh cong",     # Bắt đáy thành công
    "giai cuu thanh cong",    # Giải cứu thành công
    "cau vao manh",           # Cầu vào mạnh
    "lan toa",                # Dòng tiền lan tỏa
    "dan song",               # Dẫn sóng thị trường
    "dong thuan tang",        # Đồng thuận tăng
    "dong loat tang tran",    # Đồng loạt tăng trần
    "xanh bat ngat",          # Xanh bạt ngàn
)

# 1.3. Tiếng lóng diễn đàn, Tâm lý tạo lập & Tín hiệu ngầm (Slang & Undercover Signals)
POSITIVE_SLANG_TERMS: tuple[str, ...] = (
    "bim bip",                # Bìm bịp (phe kỳ vọng thị trường tăng)
    "ve bo",                  # Về bờ (thoát lỗ)
    "doi lai gom",            # Đội lái gom hàng
    "tay to gom",             # Tay to gom
    "tay to vao hang",        # Tay to vào hàng
    "ca map vao hang",        # Cá mập vào hàng
    "lai keo",                # Đội lái kéo
    "be chart",               # Bẻ chart (phá vỡ chỉ báo kỹ thuật giảm)
    "bo doi ve lang",         # Bộ đội về làng (dòng tiền lớn vào giải cứu)
    "boc dau",                # Bốc đầu (giá phi mạnh)
    "sieu co",                # Siêu cổ phiếu
    "sieu co phieu",          # Siêu cổ phiếu
    "vao song",               # Vào sóng tăng
    "chan song",              # Chân sóng đại hội
    "chay nuoc rut",          # Chạy nước rút
    "thau tom",               # Thâu tóm doanh nghiệp
    "chim lon chuyen gioi",   # Chim lợn chuyển giới thành bìm bịp
    "chuyen gioi thanh bim bip",# Chuyển giới sang mua
    "ho room ngoai",          # Hở room ngoại (cơ hội ngoại gom)
)

# 1.4. Từ láy biểu cảm trạng thái tích cực trong tiếng Việt (Expressive Reduplications)
POSITIVE_EXPRESSIVE_TERMS: tuple[str, ...] = (
    "ron rang",               # Rộn ràng
    "tung bung",              # Tưng bừng
    "vung chai",              # Vững chãi
    "nong am",                # Nóng ấm
    "sang sua",               # Sáng sủa
    "dat dao",                # Dạt dào
)

POSITIVE_TERMS: tuple[str, ...] = (
    POSITIVE_CORPORATE_TERMS
    + POSITIVE_MARKET_TERMS
    + POSITIVE_SLANG_TERMS
    + POSITIVE_EXPRESSIVE_TERMS
)

# =============================================================================
# 2. NEGATIVE LEXICON TAXONOMY (Từ vựng Tiêu cực Đa tầng)
# =============================================================================

# 2.1. Thua lỗ, Rủi ro thanh toán & Pháp lý (Corporate Distress & Legal Risks)
NEGATIVE_CORPORATE_TERMS: tuple[str, ...] = (
    "thua lo",                # Thua lỗ
    "lo rong",                # Lỗ ròng
    "lo luy ke",              # Lỗ lũy kế
    "lo nang",                # Lỗ nặng
    "loi nhuan giam",         # Lợi nhuận giảm
    "doanh thu giam",         # Doanh thu giảm
    "sut giam",               # Sụt giảm
    "giam manh",              # Giảm mạnh
    "tut doc",                # Tụt dốc
    "hut hoi",                # Hụt hơi
    "kem sac",                # Kém sắc
    "khong dat ke hoach",     # Không đạt kế hoạch
    "dinh tre",               # Đình trệ
    "ngung hoat dong",        # Ngừng hoạt động
    "kho khan bua vay",       # Khó khăn bủa vây
    "ap luc tra no",          # Áp lực trả nợ
    "mat thanh khoan",        # Mất thanh khoản
    "thieu hut von",          # Thiếu hụt vốn
    "no xau",                 # Nợ xấu
    "no dong",                # Nợ đọng
    "no qua han",             # Nợ quá hạn
    "mat kha nang thanh toan",# Mất khả năng thanh toán
    "khung hoang",            # Khủng hoảng
    "canh bao",               # Cảnh báo (diện cảnh báo)
    "kiem soat",              # Bị đưa vào diện kiểm soát
    "vi pham",                # Vi phạm
    "xu phat",                # Xử phạt hành chính / tiền
    "rut von",                # Rút vốn
    "thoai von",              # Thoái vốn tháo chạy
    "kien tung",              # Kiện tụng
    "tranh chap",             # Tranh chấp nội bộ
    "sa thai",                # Sa thải nhân sự
    "cat giam",               # Cắt giảm biên chế
    "dinh chi",               # Đình chỉ hoạt động / giao dịch
    "huy niem yet",           # Hủy niêm yết
    "kiem toan tu choi",      # Kiểm toán từ chối đưa ý kiến
    "y kien ngoai tru",       # Ý kiến kiểm toán ngoại trừ
    "gian lan",               # Gian lận báo cáo
    "khoi to",                # Khởi tố vụ án
    "bat tam giam",           # Bắt tạm giam lãnh đạo
    "thanh tra",              # Bị thanh tra đột xuất
    "phat hanh chui",         # Phát hành chui / bán chui
    "thao tung gia",          # Thao túng giá chứng khoán
    "cham tra no trai phieu", # Chậm trả nợ trái phiếu
    "vi pham cong bo thong tin", # Vi phạm công bố thông tin
    "suy thoai",              # Suy thoái
    "pha san",                # Phá sản
    "giai the",               # Giải thể
)

# 2.2. Bán tháo, Giải chấp & Kẹt thanh khoản (Market Distress & Margin Liquidation)
NEGATIVE_MARKET_TERMS: tuple[str, ...] = (
    "ban thao",               # Bán tháo
    "thao cong",              # Tháo cống
    "giai chap",              # Bị giải chấp cổ phiếu
    "force sell",             # Force sell lệnh bán ép buộc
    "call margin",            # Bị gọi ký quỹ
    "trang ben mua",          # Trắng bên mua (mất thanh khoản chiều mua)
    "mua ben trang",          # Múa bên trăng (tiếng lóng trắng bên mua)
    "xanh lo",                # Xanh lơ (giảm kịch sàn)
    "lau san",                # Lau sàn (giảm sàn la liệt)
    "giam san",               # Giảm sàn
    "chat san",               # Chất lệnh bán giá sàn
    "khoi ngoai ban rong",    # Khối ngoại bán ròng
    "xa hang",                # Xả hàng
    "xa hang loat",           # Xả hàng loạt
    "phan phoi dinh",         # Phân phối đỉnh
    "thung day",              # Thủng đáy lịch sử
    "thung ho tro",           # Thủng ngưỡng hỗ trợ
    "gay nen",                # Gãy nền giá
    "dong bang thanh khoan",  # Đóng băng thanh khoản
    "tat thanh khoan",        # Tắt thanh khoản
    "dap tru",                # Đạp trụ (ép chỉ số giảm)
    "giam sau",               # Giảm sâu
    "roi thang dung",         # Rơi thẳng đứng
)

# 2.3. Tiếng lóng diễn đàn, Tâm lý dẫn dắt & Cạm bẫy (Slang & Deceptive Traps)
NEGATIVE_SLANG_TERMS: tuple[str, ...] = (
    "chim lon",               # Chim lợn (phe hô hào thị trường sập)
    "up bo",                  # Úp bô (bán tháo lên đầu nhà đầu tư nhỏ lẻ)
    "lua ga",                 # Lùa gà (dụ dỗ nhỏ lẻ vào bẫy)
    "du dinh",                # Đu đỉnh
    "kep hang",               # Kẹp hàng (không bán được)
    "kep bo",                 # Kẹp bô
    "roi tu do",              # Rơi tự do
    "bay tang gia",           # Bẫy tăng giá (bull trap)
    "bull trap",              # Bull trap
    "lai xa",                 # Lái xả hàng
    "chay tai khoan",         # Cháy tài khoản
    "chay margin",            # Cháy margin
    "cua chan ban",           # Cưa chân bàn (thua lỗ từ từ mỗi ngày một ít)
)

# 2.4. Từ láy biểu đạt sắc thái trạng thái tiêu cực trong tiếng Việt (Expressive Reduplications)
NEGATIVE_EXPRESSIVE_TERMS: tuple[str, ...] = (
    "lao doc",                # Lao dốc
    "ngup lan",               # Ngụp lặn
    "lay lat",                # Lay lắt
    "chap chung",             # Chập chững
    "dap dinh",               # Dập dình
    "bap benh",               # Bấp bênh
    "thoi thop",              # Thoi thóp
    "i ach",                  # Ì ạch
    "nho giot",               # Nhỏ giọt
    "dieu dung",              # Điêu đứng
    "tang thuong",            # Tang thương
    "chao dao",               # Chao đảo
    "be tac",                 # Bế tắc
    "chong chanh",            # Chông chênh
    "lao dao",                # Lao đao
)

NEGATIVE_TERMS: tuple[str, ...] = (
    NEGATIVE_CORPORATE_TERMS
    + NEGATIVE_MARKET_TERMS
    + NEGATIVE_SLANG_TERMS
    + NEGATIVE_EXPRESSIVE_TERMS
)

# =============================================================================
# 3. TIỀN TỐ PHỦ ĐỊNH TRONG TIẾNG VIỆT (Negation Handling Rules)
# =============================================================================
# Khi tiền tố phủ định đi liền trước một từ vựng, sắc thái sẽ bị đảo ngược:
# "không tăng trưởng" -> Tiêu cực (Negative)
# "chấm dứt thua lỗ", "ngừng giảm" -> Tích cực (Positive)
NEGATION_PREFIXES: tuple[str, ...] = (
    "khong",
    "chua",
    "chang",
    "ngung",
    "cham dut",
    "kho co the",
    "kho",
    "het",
    "dut mach",
)


def _strip_accents_lower(text: str) -> str:
    """Lowercase and strip Vietnamese diacritics for robust substring matching.

    Uses NFD decomposition + combining-mark removal, which handles standard
    Vietnamese Unicode text. Does not special-case "d" vs "đ" beyond what
    NFD naturally produces (đ decomposes to a base 'd' plus a stroke that
    NFD does not treat as a combining mark in all normalizers -- see the
    explicit .replace() below, which is a known NFD gap for Vietnamese).
    """
    text = text.lower()
    text = text.replace("đ", "d")
    nfd = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn")


def score_headline(headline: str) -> float:
    """Return a sentiment score in [-1.0, 1.0] for a single VN headline.

    Score = (positive_hits - negative_hits) / (positive_hits + negative_hits),
    clipped to [-1, 1]. Returns 0.0 (neutral) if no lexicon term matches.

    Linguistic enhancements:
    1. Multi-tier lexicon matching (Corporate, Market Action, Slang, Expressive Reduplications).
    2. Substring matching ordered by length to capture full compounds first.
    3. Negation scope detection: If a negation prefix precedes a positive term
       (e.g., "khong tang truong", "chua the but pha"), it flips to negative.
       If preceding a negative term (e.g., "cham dut thua lo", "ngung giam"),
       it flips to positive.
    """
    if not headline:
        return 0.0
    normalized = _strip_accents_lower(headline)

    def has_negation_prefix(text: str, start_idx: int) -> bool:
        """Check if any negation prefix occurs immediately before start_idx within the same clause."""
        prefix_window = text[max(0, start_idx - 16):start_idx].strip()
        # Cut off at punctuation or adversative connectors
        for sep in [",", ".", ";", "-", ":", " nhung ", " song ", " tuy nhien "]:
            if sep in prefix_window:
                prefix_window = prefix_window.split(sep)[-1].strip()
        for neg in NEGATION_PREFIXES:
            if prefix_window == neg or prefix_window.endswith(" " + neg):
                return True
        return False

    # Sort terms by descending length so compound phrases take precedence
    sorted_pos = sorted(POSITIVE_TERMS, key=len, reverse=True)
    sorted_neg = sorted(NEGATIVE_TERMS, key=len, reverse=True)

    pos_hits = 0
    neg_hits = 0
    matched_spans: list[tuple[int, int]] = []

    # Check positive terms
    for term in sorted_pos:
        idx = 0
        while True:
            pos_idx = normalized.find(term, idx)
            if pos_idx == -1:
                break
            span = (pos_idx, pos_idx + len(term))
            if not any(s[0] <= span[0] and span[1] <= s[1] for s in matched_spans):
                matched_spans.append(span)
                if has_negation_prefix(normalized, span[0]):
                    neg_hits += 1  # Flipped by negation! e.g. "không tăng trưởng"
                else:
                    pos_hits += 1
            idx = pos_idx + len(term)

    # Check negative terms
    for term in sorted_neg:
        idx = 0
        while True:
            neg_idx = normalized.find(term, idx)
            if neg_idx == -1:
                break
            span = (neg_idx, neg_idx + len(term))
            if not any(s[0] <= span[0] and span[1] <= s[1] for s in matched_spans):
                matched_spans.append(span)
                if has_negation_prefix(normalized, span[0]):
                    pos_hits += 1  # Flipped by negation! e.g. "chấm dứt thua lỗ"
                else:
                    neg_hits += 1
            idx = neg_idx + len(term)

    total = pos_hits + neg_hits
    if total == 0:
        return 0.0
    score = (pos_hits - neg_hits) / total
    return max(-1.0, min(1.0, score))


def classify_headline(headline: str, neutral_band: float = 0.0) -> str:
    """Classify a headline into 'positive' / 'negative' / 'neutral'.

    neutral_band: scores with absolute value <= neutral_band are neutral.
    Default 0.0 means only an exact tie (or no lexicon hits) is neutral --
    any net-positive or net-negative score is classified accordingly. This
    default is a STATED ASSUMPTION (see module docstring); widen
    neutral_band if a future labeled sample shows near-zero scores are
    mostly noise rather than genuine weak sentiment.
    """
    score = score_headline(headline)
    if abs(score) <= neutral_band:
        return "neutral"
    return "positive" if score > 0 else "negative"


# Precompiled for reference/inspection only -- not used in the hot path,
# since substring `in` checks on a short list are already fast enough for
# this repo's data volumes (see conventions.md A2, no premature optimization).
_ALL_TERMS_PATTERN = re.compile(
    "|".join(re.escape(t) for t in POSITIVE_TERMS + NEGATIVE_TERMS)
)