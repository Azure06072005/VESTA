"""src/pipeline/batch_entity_resolution.py

Phân hệ xử lý theo lô (Batch Processor) quy mô lớn cho F105:
Ánh xạ thực thể tin tức sang dữ liệu cơ bản & gán nhãn cổng liên quan tài chính.
Hỗ trợ chạy mẫu `--sample-size` và chạy toàn bộ `--full-run` với DuckDB bulk persistence.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from typing import List, Optional, Tuple

import duckdb
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from pipeline.news_fundamental_entity_matcher import (
    DEFAULT_NEWS_DB,
    DEFAULT_SNAPSHOT_DB,
    FinancialRelevanceClassifier,
    FundamentalEntityRegistry,
    ensure_entity_tables,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("batch_entity_resolution")


def run_batch_entity_resolution(
    news_db_path: str = DEFAULT_NEWS_DB,
    snapshot_db_path: str = DEFAULT_SNAPSHOT_DB,
    sample_size: Optional[int] = 10000,
    batch_size: int = 5000,
) -> dict:
    """Thực thi xử lý theo lô cho tin tức chưa gắn mã (symbol IS NULL) có toàn văn (body)."""
    t_start = time.time()
    logger.info("=" * 70)
    logger.info("KHỞI ĐỘNG PHÂN HỆ XỬ LÝ THEO LÔ F105 (BATCH ENTITY RESOLUTION)")
    logger.info(f"News DB: {news_db_path} | Snapshot DB: {snapshot_db_path}")
    logger.info(f"Sample Size: {sample_size if sample_size else 'FULL RUN (479,268)'} | Batch Size: {batch_size}")
    logger.info("=" * 70)

    # 1. Khởi tạo Registry & Classifier
    registry = FundamentalEntityRegistry(db_path=snapshot_db_path)
    registry.load_registry()
    classifier = FinancialRelevanceClassifier()

    # 2. Kết nối CSDL DuckDB
    con = duckdb.connect(news_db_path)
    ensure_entity_tables(con)

    limit_clause = f"LIMIT {sample_size}" if sample_size else ""
    query_articles = f"""
        SELECT n.source_url, n.source, n.headline, r.body
        FROM core.news n
        JOIN core.news_resources r ON n.source_url = r.source_url
        WHERE (n.symbol IS NULL OR trim(n.symbol) = '')
          AND r.body IS NOT NULL AND length(trim(r.body)) > 50
        ORDER BY n.source, n.source_url
        {limit_clause};
    """
    logger.info("Đang truy vấn danh sách bài viết từ Lakehouse...")
    articles = con.execute(query_articles).fetchall()
    total_articles = len(articles)
    logger.info(f"Đã tải {total_articles:,} bài viết cần xử lý.")

    if total_articles == 0:
        logger.warning("Không có bài viết nào cần xử lý!")
        con.close()
        return {}

    # 3. Xử lý từng batch
    total_processed = 0
    total_entities_mapped = 0
    total_articles_with_entities = 0
    category_counts = {}

    batch_entity_records: List[Tuple] = []
    batch_relevance_records: List[Tuple] = []

    for idx, (source_url, source, headline, body) in enumerate(articles, start=1):
        # A. Trích xuất thực thể
        matched_entities = registry.match_entities_in_text(headline, body, source_url)
        has_entity = len(matched_entities) > 0

        if has_entity:
            total_articles_with_entities += 1
            for m in matched_entities:
                batch_entity_records.append((
                    m.source_url,
                    m.symbol,
                    m.entity_type,
                    m.entity_name,
                    m.entity_role,
                    m.company_type,
                    m.ownership_pct,
                    m.confidence_score,
                    m.matched_location,
                ))
            total_entities_mapped += len(matched_entities)

        # B. Phân loại tính liên quan
        cat, is_rel, score = classifier.classify_article(headline, body, has_matched_entity=has_entity)
        category_counts[cat] = category_counts.get(cat, 0) + 1
        batch_relevance_records.append((source_url, cat, is_rel, score))

        # C. Flush batch vào DuckDB
        if idx % batch_size == 0 or idx == total_articles:
            if batch_entity_records:
                df_ent = pd.DataFrame(batch_entity_records, columns=[
                    "source_url", "symbol", "entity_type", "entity_name",
                    "entity_role", "company_type", "ownership_pct",
                    "confidence_score", "matched_location"
                ])
                # Deduplicate trên khóa chính
                df_ent = df_ent.drop_duplicates(subset=["source_url", "symbol", "entity_type", "entity_name"])
                con.register("df_ent_batch", df_ent)
                con.execute("""
                    INSERT OR IGNORE INTO core.news_entity_map
                    (source_url, symbol, entity_type, entity_name, entity_role, company_type, ownership_pct, confidence_score, matched_location)
                    SELECT * FROM df_ent_batch;
                """)
                con.unregister("df_ent_batch")
                batch_entity_records.clear()

            if batch_relevance_records:
                df_rel = pd.DataFrame(batch_relevance_records, columns=[
                    "source_url", "relevance_category", "is_financial_relevant", "relevance_score"
                ])
                df_rel = df_rel.drop_duplicates(subset=["source_url"])
                con.register("df_rel_batch", df_rel)
                con.execute("""
                    INSERT OR REPLACE INTO core.news_relevance_meta
                    (source_url, relevance_category, is_financial_relevant, relevance_score)
                    SELECT * FROM df_rel_batch;
                """)
                con.unregister("df_rel_batch")
                batch_relevance_records.clear()

            elapsed = time.time() - t_start
            speed = idx / elapsed if elapsed > 0 else 0
            logger.info(
                f"Tiến độ: {idx:,}/{total_articles:,} ({idx/total_articles*100:.1f}%) | "
                f"Thực thể: {total_entities_mapped:,} | "
                f"Bài có mã: {total_articles_with_entities:,} ({total_articles_with_entities/idx*100:.1f}%) | "
                f"Tốc độ: {speed:.1f} bài/s"
            )

    total_time = time.time() - t_start
    overall_speed = total_articles / total_time if total_time > 0 else 0

    logger.info("=" * 70)
    logger.info("HOÀN THÀNH XỬ LÝ THEO LÔ F105")
    logger.info(f"Tổng thời gian: {total_time:.2f}s | Tốc độ trung bình: {overall_speed:.1f} bài/s")
    logger.info(f"Tổng bài viết đã xử lý: {total_articles:,}")
    logger.info(f"Số bài phục hồi được mã CK: {total_articles_with_entities:,} ({total_articles_with_entities/total_articles*100:.2f}%)")
    logger.info(f"Tổng số liên kết thực thể tạo mới: {total_entities_mapped:,}")
    logger.info("Phân bổ chuyên mục (Relevance Gate):")
    for cat, cnt in sorted(category_counts.items(), key=lambda x: x[1], reverse=True):
        logger.info(f"  - {cat:20s}: {cnt:6,} bài ({cnt/total_articles*100:.2f}%)")
    logger.info("=" * 70)

    con.close()
    return {
        "total_articles": total_articles,
        "articles_with_entities": total_articles_with_entities,
        "recovery_rate_pct": round(total_articles_with_entities / total_articles * 100, 2),
        "total_entities_mapped": total_entities_mapped,
        "category_counts": category_counts,
        "total_time_seconds": round(total_time, 2),
        "speed_articles_per_sec": round(overall_speed, 1),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Chạy xử lý theo lô F105 (News-to-Fundamental Entity Resolution)")
    parser.add_argument("--sample-size", type=int, default=10000, help="Số lượng mẫu bài báo cần xử lý (mặc định 10,000)")
    parser.add_argument("--full-run", action="store_true", help="Chạy toàn bộ 479,268 bài viết")
    parser.add_argument("--batch-size", type=int, default=5000, help="Kích thước batch lưu vào DuckDB")
    args = parser.parse_args()

    sample = None if args.full_run else args.sample_size
    run_batch_entity_resolution(sample_size=sample, batch_size=args.batch_size)
