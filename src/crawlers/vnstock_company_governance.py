"""src/crawlers/vnstock_company_governance.py

Crawler & Ingester cho Hồ sơ chuyên sâu (overview) và Cơ cấu Cổ đông lớn (shareholders)
từ vnstock Company API dành cho rổ VN30 và các mã niêm yết chủ chốt.

Điểm đến:
- core.company_overview: symbol, business_model, charter_capital, free_float_percentage,
  outstanding_shares, ceo_name, auditor... (PRIMARY KEY: symbol)
- core.company_shareholders: symbol, shareholder_name, shares_owned, ownership_percentage,
  update_date, source, fetched_at (PRIMARY KEY: symbol, shareholder_name)
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Optional

import duckdb
import pandas as pd

# Thêm root dự án vào sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.crawlers.db_writer import ResilientDuckDBWriter
from vnstock_data import Company

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("crawlers.vnstock_company_governance")

VN30_SYMBOLS = [
    "ACB", "BCM", "BID", "BVH", "CTG", "FPT", "GAS", "GVR", "HDB", "HPG",
    "MBB", "MSN", "MWG", "PLX", "POW", "SAB", "SHB", "SSB", "SSI", "STB",
    "TCB", "TPB", "VCB", "VHM", "VIB", "VIC", "VJC", "VNM", "VPB", "VRE",
]


class VnstockCompanyGovernanceCrawler:
    """Bộ thu thập Hồ sơ quản trị và Cổ đông lớn từ vnstock."""

    def __init__(self, writer: Optional[ResilientDuckDBWriter] = None) -> None:
        self.writer = writer or ResilientDuckDBWriter()

    def crawl_symbol(self, symbol: str) -> Dict[str, int]:
        """Thu thập overview và shareholders cho một mã cổ phiếu."""
        symbol = symbol.upper().strip()
        now = dt.datetime.now(dt.timezone.utc)
        results = {"overview": 0, "shareholders": 0}

        try:
            comp = Company(symbol=symbol)
        except Exception as e:
            logger.error("[%s] Không thể khởi tạo Company API: %s", symbol, e)
            return results

        # 1. Thu thập overview
        try:
            df_ov = comp.overview()
            if df_ov is not None and not df_ov.empty:
                df_ov["symbol"] = symbol
                df_ov["source"] = "vnstock"
                df_ov["fetched_at"] = now

                overview_cols = [
                    "symbol", "business_model", "founded_date", "charter_capital",
                    "number_of_employees", "listing_date", "par_value", "exchange",
                    "listing_price", "listed_volume", "ceo_name", "ceo_position",
                    "inspector_name", "inspector_position", "establishment_license",
                    "business_code", "tax_id", "auditor", "company_type", "address",
                    "phone", "fax", "email", "website", "branches", "history",
                    "free_float_percentage", "free_float", "outstanding_shares",
                    "as_of_date", "source", "fetched_at"
                ]
                for c in overview_cols:
                    if c not in df_ov.columns:
                        df_ov[c] = None

                df_ov_clean = df_ov[overview_cols].copy()

                def _save_ov(con: duckdb.DuckDBPyConnection) -> int:
                    con.register("df_ov_staging", df_ov_clean)
                    con.execute("""
                        INSERT INTO core.company_overview
                        SELECT * FROM df_ov_staging
                        ON CONFLICT (symbol) DO UPDATE SET
                            charter_capital = EXCLUDED.charter_capital,
                            number_of_employees = EXCLUDED.number_of_employees,
                            free_float_percentage = EXCLUDED.free_float_percentage,
                            free_float = EXCLUDED.free_float,
                            outstanding_shares = EXCLUDED.outstanding_shares,
                            ceo_name = EXCLUDED.ceo_name,
                            ceo_position = EXCLUDED.ceo_position,
                            auditor = EXCLUDED.auditor,
                            as_of_date = EXCLUDED.as_of_date,
                            fetched_at = EXCLUDED.fetched_at
                    """)
                    con.unregister("df_ov_staging")
                    return len(df_ov_clean)

                results["overview"] = self.writer.execute_with_retry(_save_ov)
        except Exception as e:
            logger.warning("[%s] Lỗi khi cào overview: %s", symbol, e)

        # 2. Thu thập shareholders
        try:
            df_sh = comp.shareholders()
            if df_sh is not None and not df_sh.empty:
                df_sh["symbol"] = symbol
                df_sh["shareholder_name"] = df_sh["name"]
                df_sh["source"] = "vnstock"
                df_sh["fetched_at"] = now

                sh_cols = [
                    "symbol", "shareholder_name", "shares_owned",
                    "ownership_percentage", "update_date", "source", "fetched_at"
                ]
                for c in sh_cols:
                    if c not in df_sh.columns:
                        df_sh[c] = None

                df_sh_clean = df_sh[sh_cols].dropna(subset=["symbol", "shareholder_name"]).copy()

                def _save_sh(con: duckdb.DuckDBPyConnection) -> int:
                    con.register("df_sh_staging", df_sh_clean)
                    con.execute("""
                        INSERT INTO core.company_shareholders
                        SELECT * FROM df_sh_staging
                        ON CONFLICT (symbol, shareholder_name) DO UPDATE SET
                            shares_owned = EXCLUDED.shares_owned,
                            ownership_percentage = EXCLUDED.ownership_percentage,
                            update_date = EXCLUDED.update_date,
                            fetched_at = EXCLUDED.fetched_at
                    """)
                    con.unregister("df_sh_staging")
                    return len(df_sh_clean)

                results["shareholders"] = self.writer.execute_with_retry(_save_sh)
        except Exception as e:
            logger.warning("[%s] Lỗi khi cào shareholders: %s", symbol, e)

        return results

    def crawl_symbols(self, symbols: List[str], delay_seconds: float = 0.5) -> Dict[str, int]:
        """Thu thập danh sách nhiều mã cổ phiếu."""
        total_res = {"overview": 0, "shareholders": 0}
        n = len(symbols)
        logger.info("=== BẮT ĐẦU CÀO QUẢN TRỊ & CỔ ĐÔNG CHO %d MÃ ===", n)

        for i, sym in enumerate(symbols, 1):
            res = self.crawl_symbol(sym)
            total_res["overview"] += res["overview"]
            total_res["shareholders"] += res["shareholders"]
            logger.info(
                "[%d/%d] %-5s -> overview: %s, shareholders: %s",
                i, n, sym,
                "OK" if res["overview"] > 0 else "FAIL/EMPTY",
                f"+{res['shareholders']}" if res["shareholders"] > 0 else "EMPTY",
            )
            if delay_seconds > 0:
                time.sleep(delay_seconds)

        logger.info(
            "=== HOÀN TẤT: %d overview, %d cổ đông lớn ===",
            total_res["overview"], total_res["shareholders"]
        )
        return total_res


def main() -> None:
    """CLI entrypoint cho bộ cào hồ sơ & cổ đông."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Vnstock Company Governance & Shareholders Crawler")
    parser.add_argument("--symbols", default="VN30", help="Danh sách mã cổ phiếu (VN30, all, hoặc VCB,HPG...)")
    parser.add_argument("--delay", type=float, default=0.3, help="Độ trễ giữa các request (giây)")
    args = parser.parse_args()

    if args.symbols.upper() == "VN30":
        symbols = VN30_SYMBOLS
    else:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    crawler = VnstockCompanyGovernanceCrawler()
    res = crawler.crawl_symbols(symbols, delay_seconds=args.delay)
    print("\n=== KẾT QUẢ CÀO QUẢN TRỊ & CỔ ĐÔNG ===")
    print(f"  Hồ sơ chuyên sâu (overview)    : {res['overview']} mã")
    print(f"  Bản ghi cổ đông lớn (shareholders): {res['shareholders']} bản ghi")


if __name__ == "__main__":
    main()
