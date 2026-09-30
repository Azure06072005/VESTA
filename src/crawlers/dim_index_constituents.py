"""
Module cào dữ liệu rổ chỉ số / nhóm ngành (Group Rooms & Index Constituents - F001c).
Hỗ trợ quản lý và phân loại các rổ chỉ số:
1. Vốn hóa & Benchmark: VN30, VN100, VNMID, VNSML, VNALL, VNX50, VNXALL, HNX30
2. Phát triển bền vững (ESG): VNSI
3. Chuyên đề & Room ngoại: VNDIAMOND, VNFINLEAD, VNFINSELECT
4. Phân ngành HOSE (10 ngành ICB): VNFIN, VNREAL, VNIT, VNMAT, VNIND, VNCONS, VNCOND, VNHEAL, VNENE, VNUTI

Nguồn dữ liệu:
- SSI iBoard API (Real-time index basket constituent feeds)
- vnstock_data (KBS provider cross-validation)
"""

import json
import logging
import os
import ssl
import urllib.request
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

import duckdb

logger = logging.getLogger(__name__)

# Metadata chuẩn của 22 rổ chỉ số chính tại TTCK Việt Nam
INDEX_CATALOG = {
    # 1. Market Cap & Benchmarks
    "VN30": {
        "name": "Chỉ số VN30",
        "exchange": "HOSE",
        "category": "BENCHMARK",
        "cycle": "SEMI_ANNUALLY",
        "description": "30 doanh nghiệp vốn hóa lớn và thanh khoản cao nhất sàn HOSE",
    },
    "VN100": {
        "name": "Chỉ số VN100",
        "exchange": "HOSE",
        "category": "MARKET_CAP",
        "cycle": "SEMI_ANNUALLY",
        "description": "100 cổ phiếu hàng đầu bao gồm rổ VN30 và VNMidCap",
    },
    "VNMID": {
        "name": "Chỉ số VNMidCap",
        "exchange": "HOSE",
        "category": "MARKET_CAP",
        "cycle": "SEMI_ANNUALLY",
        "description": "70 doanh nghiệp quy mô vốn hóa trung bình trên sàn HOSE",
    },
    "VNSML": {
        "name": "Chỉ số VNSmallCap",
        "exchange": "HOSE",
        "category": "MARKET_CAP",
        "cycle": "SEMI_ANNUALLY",
        "description": "Các doanh nghiệp quy mô vốn hóa nhỏ đạt chuẩn thanh khoản sàn HOSE",
    },
    "VNALL": {
        "name": "Chỉ số VNAllShare",
        "exchange": "HOSE",
        "category": "MARKET_CAP",
        "cycle": "SEMI_ANNUALLY",
        "description": "Toàn bộ cổ phiếu niêm yết trên HOSE đáp ứng tiêu chí sàng lọc",
    },
    "VNX50": {
        "name": "Chỉ số VNX50",
        "exchange": "VNX",
        "category": "BENCHMARK",
        "cycle": "SEMI_ANNUALLY",
        "description": "50 cổ phiếu hàng đầu thị trường chung kết hợp HOSE và HNX",
    },
    "VNXALL": {
        "name": "Chỉ số VNX AllShare",
        "exchange": "VNX",
        "category": "MARKET_CAP",
        "cycle": "SEMI_ANNUALLY",
        "description": "Tập hợp toàn bộ các cổ phiếu niêm yết trên cả hai sàn HOSE và HNX",
    },
    "HNX30": {
        "name": "Chỉ số HNX30",
        "exchange": "HNX",
        "category": "BENCHMARK",
        "cycle": "SEMI_ANNUALLY",
        "description": "30 cổ phiếu có tính thanh khoản và vốn hóa tốt nhất trên sàn HNX",
    },
    # 2. ESG (Phát triển bền vững)
    "VNSI": {
        "name": "Chỉ số Phát triển Bền vững",
        "exchange": "HOSE",
        "category": "ESG",
        "cycle": "ANNUALLY",
        "description": "20 doanh nghiệp có điểm phát triển bền vững (ESG) cao nhất trong rổ VN100",
    },
    # 3. Thematic / Foreign Room (Chuyên đề & Giới hạn sở hữu nước ngoài)
    "VNDIAMOND": {
        "name": "Chỉ số Cổ phiếu Kim Cương",
        "exchange": "HOSE",
        "category": "THEMATIC",
        "cycle": "SEMI_ANNUALLY",
        "description": "Các cổ phiếu đầu ngành có tỷ lệ sở hữu nhà đầu tư nước ngoài (FOL) chạm trần >= 95%",
    },
    "VNFINLEAD": {
        "name": "Chỉ số Ngành Tài chính Dẫn dắt",
        "exchange": "HOSE",
        "category": "THEMATIC",
        "cycle": "QUARTERLY",
        "description": "Các cổ phiếu ngành tài chính (ngân hàng, chứng khoán, bảo hiểm) đầu ngành có thanh khoản cao",
    },
    "VNFINSELECT": {
        "name": "Chỉ số Ngành Tài chính Tuyển chọn",
        "exchange": "HOSE",
        "category": "THEMATIC",
        "cycle": "SEMI_ANNUALLY",
        "description": "Tất cả các cổ phiếu thuộc ngành tài chính trên HOSE đạt yêu cầu thanh khoản",
    },
    # 4. HOSE Sector Indices (10 chỉ số ngành ICB)
    "VNFIN": {
        "name": "Chỉ số Ngành Tài chính",
        "exchange": "HOSE",
        "category": "SECTOR",
        "cycle": "SEMI_ANNUALLY",
        "description": "Các cổ phiếu thuộc ngành Tài chính trên sàn HOSE",
    },
    "VNREAL": {
        "name": "Chỉ số Ngành Bất động sản",
        "exchange": "HOSE",
        "category": "SECTOR",
        "cycle": "SEMI_ANNUALLY",
        "description": "Các cổ phiếu thuộc ngành Bất động sản trên sàn HOSE",
    },
    "VNIT": {
        "name": "Chỉ số Ngành Công nghệ Thông tin",
        "exchange": "HOSE",
        "category": "SECTOR",
        "cycle": "SEMI_ANNUALLY",
        "description": "Các cổ phiếu thuộc ngành Công nghệ Thông tin trên sàn HOSE",
    },
    "VNMAT": {
        "name": "Chỉ số Ngành Nguyên vật liệu",
        "exchange": "HOSE",
        "category": "SECTOR",
        "cycle": "SEMI_ANNUALLY",
        "description": "Các cổ phiếu thuộc ngành Nguyên vật liệu (Thép, Hóa chất) trên sàn HOSE",
    },
    "VNIND": {
        "name": "Chỉ số Ngành Công nghiệp",
        "exchange": "HOSE",
        "category": "SECTOR",
        "cycle": "SEMI_ANNUALLY",
        "description": "Các cổ phiếu thuộc ngành Công nghiệp (Xây dựng, Vận tải) trên sàn HOSE",
    },
    "VNCONS": {
        "name": "Chỉ số Ngành Tiêu dùng thiết yếu",
        "exchange": "HOSE",
        "category": "SECTOR",
        "cycle": "SEMI_ANNUALLY",
        "description": "Các cổ phiếu Thực phẩm, Đồ uống, Nông nghiệp thiết yếu trên HOSE",
    },
    "VNCOND": {
        "name": "Chỉ số Ngành Tiêu dùng không thiết yếu",
        "exchange": "HOSE",
        "category": "SECTOR",
        "cycle": "SEMI_ANNUALLY",
        "description": "Các cổ phiếu Bán lẻ, Ô tô phụ tùng, Du lịch giải trí trên HOSE",
    },
    "VNHEAL": {
        "name": "Chỉ số Ngành Chăm sóc sức khỏe",
        "exchange": "HOSE",
        "category": "SECTOR",
        "cycle": "SEMI_ANNUALLY",
        "description": "Các cổ phiếu Dược phẩm, Thiết bị y tế trên sàn HOSE",
    },
    "VNENE": {
        "name": "Chỉ số Ngành Năng lượng",
        "exchange": "HOSE",
        "category": "SECTOR",
        "cycle": "SEMI_ANNUALLY",
        "description": "Các cổ phiếu Dầu khí, Khai thác than & Năng lượng trên HOSE",
    },
    "VNUTI": {
        "name": "Chỉ số Ngành Tiện ích",
        "exchange": "HOSE",
        "category": "SECTOR",
        "cycle": "SEMI_ANNUALLY",
        "description": "Các cổ phiếu Điện, Nước, Khí đốt tiện ích trên sàn HOSE",
    },
}


def fetch_ssi_group_symbols(group_code: str) -> List[str]:
    """Lấy danh sách mã chứng khoán trong rổ chỉ số từ SSI iBoard API."""
    url = f"https://iboard-query.ssi.com.vn/stock/group/{group_code}"
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
    )
    with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
        data = payload.get("data", [])
        symbols = [item["stockSymbol"].strip().upper() for item in data if "stockSymbol" in item]
        return sorted(list(set(symbols)))


_KBS_LISTING_CACHE = None

def get_kbs_listing():
    """Lấy hoặc khởi tạo instance Listing(source='kbs') dùng chung."""
    global _KBS_LISTING_CACHE
    if _KBS_LISTING_CACHE is None:
        try:
            from vnstock_data import Listing
            _KBS_LISTING_CACHE = Listing(source="kbs")
        except Exception as e:
            logger.debug(f"Không thể khởi tạo Listing(source='kbs'): {e}")
            _KBS_LISTING_CACHE = False
    return _KBS_LISTING_CACHE if _KBS_LISTING_CACHE is not False else None


def fetch_vnstock_kbs_group(group_code: str) -> Optional[List[str]]:
    """Lấy danh sách mã từ vnstock (KBS source) để đối soát nếu khả dụng."""
    try:
        ls = get_kbs_listing()
        if not ls:
            return None

        # Map tên tương ứng của KBS
        kbs_map = {
            "VN30": "VN30",
            "VN100": "VN100",
            "VNMID": "VNMidCap",
            "VNSML": "VNSmallCap",
            "VNALL": "VNALL",
            "VNX50": "VNX50",
            "VNXALL": "VNXALL",
            "HNX30": "HNX30",
            "VNSI": "VNSI",
        }
        kbs_group = kbs_map.get(group_code)
        if not kbs_group:
            return None
        res = ls.symbols_by_group(kbs_group)
        symbols = res.tolist() if hasattr(res, "tolist") else list(res)
        return sorted([str(s).strip().upper() for s in symbols])
    except Exception as e:
        logger.debug(f"KBS cross-validation fetch skipped for {group_code}: {e}")
        return None


def get_default_db_path() -> str:
    """Xác định đường dẫn DuckDB chính (ưu tiên vesta_snapshot.duckdb)."""
    snapshot_path = "d:/VESTA/db/vesta_snapshot.duckdb"
    if os.path.exists(snapshot_path):
        return snapshot_path
    return "d:/VESTA/db/vesta.duckdb"


def sync_index_metadata(con: duckdb.DuckDBPyConnection) -> int:
    """Đồng bộ bảng core.dim_index_metadata với danh mục 22 rổ chỉ số chuẩn."""
    rows = []
    for code, info in INDEX_CATALOG.items():
        rows.append((
            code,
            info["name"],
            info["exchange"],
            info["category"],
            info["description"],
            info["cycle"],
        ))

    con.executemany(
        """
        INSERT INTO core.dim_index_metadata (
            index_code, index_name, exchange, category, description, rebalance_cycle
        ) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT (index_code) DO UPDATE SET
            index_name = EXCLUDED.index_name,
            exchange = EXCLUDED.exchange,
            category = EXCLUDED.category,
            description = EXCLUDED.description,
            rebalance_cycle = EXCLUDED.rebalance_cycle
        """,
        rows,
    )
    return len(rows)


def crawl_and_sync_constituents(
    db_path: Optional[str] = None,
    effective_date: Optional[date] = None,
    verify_with_kbs: bool = False,
    con: Optional[duckdb.DuckDBPyConnection] = None,
) -> Dict[str, int]:
    """
    Cào toàn bộ 22 rổ chỉ số và lưu vào core.dim_index_constituents.
    Đảm bảo chỉ ghi vào database chính, không đụng tới backup database.
    """
    own_con = False
    if con is None:
        if db_path is None:
            db_path = get_default_db_path()
        con = duckdb.connect(db_path)
        own_con = True

    if effective_date is None:
        effective_date = date.today()

    now_ts = datetime.now()

    # 1. Đồng bộ Metadata
    metadata_count = sync_index_metadata(con)
    logger.info(f"Đã đồng bộ {metadata_count} chỉ số vào core.dim_index_metadata.")

    summary = {}
    total_inserted = 0

    for index_code in INDEX_CATALOG.keys():
        try:
            # Lấy danh sách mã từ SSI iBoard (tốc độ cao ~0.2s/rổ)
            symbols = fetch_ssi_group_symbols(index_code)
            source = "SSI_IBOARD"

            # Đối soát với KBS nếu rổ thuộc nhóm chuẩn và có cờ verify_with_kbs
            if verify_with_kbs:
                kbs_symbols = fetch_vnstock_kbs_group(index_code)
                if kbs_symbols and len(kbs_symbols) == len(symbols):
                    source = "SSI_IBOARD+KBS_VERIFIED"

            insert_rows = []
            for rank, sym in enumerate(symbols, start=1):
                insert_rows.append((
                    index_code,
                    sym,
                    None,  # weight
                    rank,
                    effective_date,
                    True,  # is_current
                    source,
                    now_ts,
                ))

            # Upsert vào core.dim_index_constituents
            con.executemany(
                """
                INSERT INTO core.dim_index_constituents (
                    index_code, symbol, weight, rank, effective_date, is_current, source, fetched_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (index_code, symbol, effective_date) DO UPDATE SET
                    rank = EXCLUDED.rank,
                    is_current = EXCLUDED.is_current,
                    source = EXCLUDED.source,
                    fetched_at = EXCLUDED.fetched_at
                """,
                insert_rows,
            )

            summary[index_code] = len(symbols)
            total_inserted += len(symbols)
            logger.info(f"Rổ {index_code:12} ({source}): đã lưu {len(symbols)} mã.")

        except Exception as e:
            logger.error(f"Lỗi khi cào rổ {index_code}: {e}")
            summary[index_code] = 0

    if own_con:
        con.close()
    logger.info(f"Hoàn thành cào F001c: Tổng cộng {total_inserted} lượt phân bổ vào 22 rổ.")
    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    crawl_and_sync_constituents()
