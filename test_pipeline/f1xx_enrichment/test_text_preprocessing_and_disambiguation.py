"""test_pipeline/f1xx_enrichment/test_text_preprocessing_and_disambiguation.py

Step 5: Text Preprocessing, Deduplication & Entity Disambiguation for VESTA.
Processes 278k macro_policy documents and 661k-1.1M news articles:
1. Text Normalization: NFC encoding, administrative boilerplate stripping, HTML cleaning.
2. Policy Taxonomy Classification: Categorizes macro policies into 5 pillars + misrouted filter.
3. Entity Disambiguation & Sector Linkage: Solves SBV vs Commercial Bank disambiguation and maps to sectors.
4. MinHash LSH Deduplication: Finds exact and near-duplicate syndicated news/policies.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

import duckdb
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

DB_PATH = "db/test_db/vesta_test.duckdb"
OUT_REPORT = "test_pipeline/out/text_preprocessing_report.json"

# =====================================================================
# 1. TEXT NORMALIZATION & BOILERPLATE PATTERNS
# =====================================================================
HTML_PATTERN = re.compile(r"<[^>]+>")
WHITESPACE_PATTERN = re.compile(r"\s+")

# Media / Source footers & headers
SOURCE_STAMPS = re.compile(
    r"(?i)"
    r"\(chinhphu\.vn\)\s*-\s*|"
    r"\(thoibaonganhang\.vn\)\s*-\s*|"
    r"\b(?:nóng|tin\s+nóng|nóng\s+trong\s+ngày|tin\s+nhanh):\s*|"
    r"\btheo\s+(?:cafef|vietstock|tin\s+nhanh\s+chứng\s+khoán|tuổi\s+trẻ|báo\s+đầu\s+tư|vneconomy|nhân\s+dân|tiền\s+phong|tnck)[^.\n]*|"
    r"\bảnh:\s*[^.\n]*|"
    r"\bnguồn:\s*[^.\n]*|"
    r"\bbài(?:\s+và\s+ảnh)?:\s*[^.\n]*"
)

# Administrative document headers / footers
ADMIN_BOILERPLATE = re.compile(
    r"\b(?i:"
    r"cộng\s+hòa\s+xã\s+hội\s+chủ\s+nghĩa\s+việt\s+nam|"
    r"độc\s+lập\s*-\s*tự\s+do\s*-\s*hạnh\s+phúc|"
    r"căn\s+cứ\s+luật[^.\n]*|"
    r"nơi\s+nhận:\s*[^.\n]*|"
    r"ký\s+thay\s+thủ\s+tướng[^.\n]*|"
    r"thay\s+mặt\s+chính\s+phủ[^.\n]*|"
    r"thay\s+mặt\s+bộ\s+trưởng[^.\n]*"
    r")"
)


def normalize_text(text: str, is_policy: bool = False) -> str:
    """Normalizes Vietnamese text: NFC format, cleans HTML, strips administrative boilerplate."""
    if not text or not isinstance(text, str):
        return ""
    # 1. Unicode NFC
    t = unicodedata.normalize("NFC", text)
    # 2. HTML
    t = HTML_PATTERN.sub(" ", t)
    # 3. Media Stamps
    t = SOURCE_STAMPS.sub(" ", t)
    # 4. Admin boilerplate if policy doc
    if is_policy:
        t = ADMIN_BOILERPLATE.sub(" ", t)
    # 5. Whitespace
    t = WHITESPACE_PATTERN.sub(" ", t).strip()
    return t


# =====================================================================
# 2. MACRO POLICY PILLARS & TAXONOMY CLASSIFIER
# =====================================================================
POLICY_PILLARS = {
    "MONETARY": {
        "name": "Chính sách Tiền tệ & Lãi suất",
        "pattern": re.compile(
            r"\b(?i:lãi\s+suất|trần\s+lãi\s+suất|lãi\s+suất\s+điều\s+hành|tái\s+cấp\s+vốn|omo|nghiệp\s+vụ\s+thị\s+trường\s+mở|"
            r"trần\s+tín\s+dụng|room\s+tín\s+dụng|dự\s+trữ\s+bắt\s+buộc|tỷ\s+giá|tỷ\s+giá\s+trung\s+tâm|thông\s+tư\s+02|thông\s+tư\s+06|"
            r"nợ\s+xấu|bơm\s+tiền|hút\s+tiền|tín\s+phiếu|ngân\s+hàng\s+nhà\s+nước|nhnn|thống\s+đốc)\b"
        ),
        "primary_sectors": [11, 3, 5],  # Ngân hàng, BĐS, Chứng khoán
    },
    "FISCAL_INFRASTRUCTURE": {
        "name": "Tài khóa, Thuế & Đầu tư công",
        "pattern": re.compile(
            r"\b(?i:đầu\s+tư\s+công|giải\s+ngân|cao\s+tốc|sân\s+bay\s+long\s+thành|bộ\s+giao\s+thông|giảm\s+thuế\s+vat|"
            r"miễn\s+giảm\s+thuế|ngân\s+sách|kho\s+bạc|vốn\s+nhà\s+nước|dự\s+án\s+trọng\s+điểm)\b"
        ),
        "primary_sectors": [24, 21],  # Xây dựng, Vật liệu xây dựng
    },
    "REAL_ESTATE_BONDS": {
        "name": "Bất động sản & Trái phiếu doanh nghiệp",
        "pattern": re.compile(
            r"\b(?i:nghị\s+định\s+08|nghị\s+định\s+65|trái\s+phiếu\s+doanh\s+nghiệp|tpdn|gỡ\s+vướng\s+pháp\s+lý|"
            r"nhà\s+ở\s+xã\s+hội|luật\s+đất\s+đai|luật\s+nhà\s+ở|luật\s+kinh\s+doanh\s+bất\s+động\s+sản|bộ\s+xây\s+dựng|"
            r"dự\s+án\s+bất\s+động\s+sản|thị\s+trường\s+bất\s+động\s+sản)\b"
        ),
        "primary_sectors": [3, 11],  # Bất động sản, Ngân hàng
    },
    "CAPITAL_MARKETS": {
        "name": "Thị trường Chứng khoán & Nâng hạng",
        "pattern": re.compile(
            r"\b(?i:ủy\s+ban\s+chứng\s+khoán|ubcknn|nâng\s+hạng|ftse|msci|hệ\s+thống\s+krx|non-prefunding|thông\s+tư\s+68|"
            r"giao\s+dịch\s+ký\s+quỹ|margin|thanh\s+tra\s+chứng\s+khoán|công\s+ty\s+chứng\s+khoán|sở\s+giao\s+dịch)\b"
        ),
        "primary_sectors": [5],  # Chứng khoán
    },
    "ENERGY_TRADE": {
        "name": "Năng lượng, Xuất nhập khẩu & Thương mại",
        "pattern": re.compile(
            r"\b(?i:quy\s+hoạch\s+điện|giá\s+điện|evn|xăng\s+dầu|chống\s+bán\s+phá\s+giá|thuế\s+tự\s+vệ|"
            r"xuất\s+khẩu\s+thủy\s+sản|xuất\s+khẩu\s+gạo|dệt\s+may|bộ\s+công\s+thương)\b"
        ),
        "primary_sectors": [10, 21, 18],  # Dầu khí, VLXD/Thép, Hóa chất
    },
    "MISROUTED_CORPORATE": {
        "name": "Tin Doanh nghiệp / Cổ tức bị lẫn vào Macro Policy",
        "pattern": re.compile(
            r"\b(?i:ngày\s+gdkhq|trả\s+cổ\s+tức|tạm\s+ứng\s+cổ\s+tức|bctc|báo\s+cáo\s+tài\s+chính|đhđcđ|"
            r"nghị\s+quyết\s+hđqt|cổ\s+đông\s+lớn|chào\s+mua\s+công\s+khai|thâu\s+tóm|mua\s+lại\s+cổ\s+phiếu)\b"
        ),
        "primary_sectors": [],  # Phải điều hướng sang corporate news
    },
}


# =====================================================================
# 3. ENTITY DISAMBIGUATION: SBV VS. COMMERCIAL BANKS
# =====================================================================
SBV_PATTERNS = re.compile(r"\b(?i:ngân\s+hàng\s+nhà\s+nước|nhnn|thống\s+đốc\s+ngân\s+hàng|nhnn\s+chi\s+nhánh)\b")
COMMERCIAL_BANK_CONTEXT = re.compile(
    r"\b(?i:ngân\s+hàng\s+thương\s+mại|các\s+tổ\s+chức\s+tín\s+dụng|các\s+tctd|nhóm\s+ngân\s+hàng|cổ\s+phiếu\s+ngân\s+hàng|"
    r"dòng\s+bank|room\s+tín\s+dụng|lãi\s+suất\s+cho\s+vay|lãi\s+suất\s+huy\s+động|nợ\s+xấu|vcb|bid|ctg|tcb|mbb|acb|vpbank)\b"
)


def disambiguate_banking_entities(headline: str, body: str) -> Tuple[bool, bool]:
    """Returns (is_sbv_policy_maker, is_commercial_banking_sector).
    Enforces strict separation: SBV mentions alone DO NOT trigger sector 11.
    """
    full_text = f"{headline} {body}"
    has_sbv = bool(SBV_PATTERNS.search(full_text))
    has_comm_bank = bool(COMMERCIAL_BANK_CONTEXT.search(full_text))
    
    # If it only mentions "Ngân hàng Nhà nước" and has no commercial bank operational context,
    # it is a Policy Maker document, NOT the Commercial Banking Sector.
    is_sector_11 = has_comm_bank
    return has_sbv, is_sector_11


def resolve_shareholder_entity(headline: str, body: str = "") -> Optional[str]:
    """Resolves ticker symbol if article mentions a key shareholder or executive
    from core.company_shareholders (vesta_snapshot.duckdb).
    """
    try:
        from pipeline.shareholder_entity_matcher import shareholder_registry
        if not shareholder_registry._is_loaded:
            shareholder_registry.load_registry()
        return shareholder_registry.resolve_symbol_from_news(headline, body)
    except Exception:
        return None



# =====================================================================
# 4. MINHASH LSH DEDUPLICATION ENGINE
# =====================================================================
class MinHashLSH:
    """MinHash Locality-Sensitive Hashing for Near-Duplicate Text Detection."""
    def __init__(self, num_perm: int = 64, num_bands: int = 16, k_shingle: int = 3):
        self.num_perm = num_perm
        self.num_bands = num_bands
        self.rows_per_band = num_perm // num_bands  # 4
        self.k_shingle = k_shingle
        
        # Prime for hashing
        self.prime = 4294967311  # 2^32 + 15
        np.random.seed(42)
        self.a = np.random.randint(1, self.prime - 1, size=num_perm, dtype=np.int64)
        self.b = np.random.randint(0, self.prime - 1, size=num_perm, dtype=np.int64)
        
        # LSH buckets: dict of (band_idx, band_hash) -> list of doc_ids
        self.buckets = defaultdict(list)
        self.signatures = {}
        self.doc_texts = {}

    def _get_shingles(self, text: str) -> Set[int]:
        """Extracts hashed word bi-grams (2-word phrases) to avoid false collisions on short Vietnamese syllables."""
        words = text.lower().split()
        if len(words) < 2:
            return {int(hashlib.md5(text.encode("utf-8")).hexdigest()[:8], 16)}
        shingles = set()
        for i in range(len(words) - 1):
            phrase = f"{words[i]} {words[i+1]}"
            sh_h = int(hashlib.md5(phrase.encode("utf-8")).hexdigest()[:8], 16)
            shingles.add(sh_h)
        return shingles

    def compute_signature(self, text: str) -> np.ndarray:
        """Computes MinHash signature vector of length num_perm."""
        shingles = self._get_shingles(text)
        if not shingles:
            return np.zeros(self.num_perm, dtype=np.int64)
        sh_arr = np.array(list(shingles), dtype=np.int64)  # shape (N_shingles,)
        
        # Vectorized minhash: h = (a * x + b) % prime
        # a: (P,), sh_arr: (S,) -> (P, S)
        hashes = (np.outer(self.a, sh_arr) + self.b[:, None]) % self.prime
        sig = np.min(hashes, axis=1)
        return sig

    def index_document(self, doc_id: str, text: str):
        sig = self.compute_signature(text)
        self.signatures[doc_id] = sig
        self.doc_texts[doc_id] = text
        
        # Insert into LSH bands
        for b_idx in range(self.num_bands):
            band_sig = tuple(sig[b_idx * self.rows_per_band : (b_idx + 1) * self.rows_per_band])
            band_key = (b_idx, band_sig)
            self.buckets[band_key].append(doc_id)

    def find_near_duplicates(self, threshold: float = 0.75) -> List[Tuple[str, str, float]]:
        """Finds candidate pairs and verifies exact Jaccard similarity of signatures."""
        candidates = set()
        for bucket in self.buckets.values():
            if len(bucket) > 1:
                for i in range(len(bucket)):
                    for j in range(i + 1, len(bucket)):
                        id1, id2 = bucket[i], bucket[j]
                        if id1 != id2:
                            candidates.add(tuple(sorted((id1, id2))))
                            
        duplicates = []
        for id1, id2 in candidates:
            sig1 = self.signatures[id1]
            sig2 = self.signatures[id2]
            est_jaccard = np.mean(sig1 == sig2)
            if est_jaccard >= threshold:
                duplicates.append((id1, id2, float(est_jaccard)))
        return duplicates


# =====================================================================
# 5. AUDIT EXECUTION
# =====================================================================
def run_preprocessing_audit():
    print("=" * 75)
    print("STEP 5: TEXT PREPROCESSING, DEDUPLICATION & DISAMBIGUATION AUDIT")
    print("=" * 75)
    
    con = duckdb.connect(DB_PATH, read_only=True)
    
    # 1. Sample 5,000 macro_policy
    print("\n[1/5] Loading 5,000 macro_policy documents...")
    df_policy = con.execute("""
        SELECT source_url, source, issuing_body, doc_type, published_at, headline, summary, body
        FROM core.macro_policy
        ORDER BY published_at DESC
        LIMIT 5000
    """).df()
    
    # 2. Sample 5,000 news articles
    print("\n[2/5] Loading 5,000 news articles...")
    df_news = con.execute("""
        SELECT source_url, source, published_at, headline, body
        FROM core.news
        ORDER BY published_at DESC
        LIMIT 5000
    """).df()
    con.close()
    
    # Process Policy Documents
    print("\n[3/5] Cleaning and Classifying Macro Policy Taxonomy...")
    policy_pillar_counts = defaultdict(int)
    policy_sectors_mapped = defaultdict(int)
    misrouted_count = 0
    sbv_policy_maker_count = 0
    sbv_commercial_bank_count = 0
    
    cleaned_policies = []
    for _, row in df_policy.iterrows():
        raw_text = f"{row['headline']} {row['summary'] or ''}"
        clean_text = normalize_text(raw_text, is_policy=True)
        
        # Pillar Classification
        matched_pillars = []
        for p_code, p_info in POLICY_PILLARS.items():
            if p_info["pattern"].search(clean_text):
                matched_pillars.append(p_code)
                policy_pillar_counts[p_code] += 1
                for sec_id in p_info["primary_sectors"]:
                    policy_sectors_mapped[sec_id] += 1
                    
        if "MISROUTED_CORPORATE" in matched_pillars:
            misrouted_count += 1
            
        # SBV vs Commercial Bank Disambiguation
        has_sbv, is_comm_bank = disambiguate_banking_entities(row["headline"], row["summary"] or "")
        if has_sbv and not is_comm_bank:
            sbv_policy_maker_count += 1
        elif has_sbv and is_comm_bank:
            sbv_commercial_bank_count += 1
            
        cleaned_policies.append({
            "doc_id": row["source_url"],
            "source": row["source"],
            "clean_text": clean_text,
            "pillars": matched_pillars,
        })
        
    # MinHash LSH Deduplication on combined sample (10,000 docs)
    print("\n[4/5] Running MinHash LSH Deduplication across Policy & News...")
    lsh = MinHashLSH(num_perm=64, num_bands=16, k_shingle=3)
    
    # Index policies
    for item in cleaned_policies:
        lsh.index_document(item["doc_id"], item["clean_text"])
        
    # Index news
    cleaned_news = []
    for _, row in df_news.iterrows():
        raw_text = f"{row['headline']} {row['body'] or ''}"
        clean_text = normalize_text(raw_text, is_policy=False)
        lsh.index_document(row["source_url"], clean_text)
        cleaned_news.append({
            "doc_id": row["source_url"],
            "clean_text": clean_text,
        })
        
    # Find Duplicates
    near_dups = lsh.find_near_duplicates(threshold=0.75)
    exact_dup_hashes = set()
    exact_dup_count = 0
    for item in cleaned_policies + cleaned_news:
        h = hashlib.md5(item["clean_text"].encode("utf-8")).hexdigest()
        if h in exact_dup_hashes:
            exact_dup_count += 1
        else:
            exact_dup_hashes.add(h)
            
    print(f" -> Exact Duplicates (MD5 identical text): {exact_dup_count} ({exact_dup_count/10000*100:.2f}%)")
    print(f" -> Near-Duplicate Pairs (MinHash Jaccard >= 0.75): {len(near_dups)} pairs")
    print(f" -> Misrouted Corporate News inside macro_policy: {misrouted_count} / 5,000 ({misrouted_count/5000*100:.2f}%)")
    print(f" -> SBV Policy Maker alone (Not Sector 11): {sbv_policy_maker_count} docs")
    print(f" -> SBV with Commercial Bank context (Mapped to Sector 11): {sbv_commercial_bank_count} docs")
    
    # Report compilation
    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sample_size": {
            "macro_policy_sampled": len(df_policy),
            "news_sampled": len(df_news),
            "total_documents": 10000,
        },
        "deduplication": {
            "exact_duplicate_count": exact_dup_count,
            "exact_duplicate_pct": round(exact_dup_count / 10000 * 100, 2),
            "near_duplicate_pairs": len(near_dups),
            "jaccard_threshold": 0.75,
        },
        "macro_policy_classification": {
            "misrouted_corporate_in_macro_policy_pct": round(misrouted_count / 5000 * 100, 2),
            "pillar_breakdown": {k: policy_pillar_counts[k] for k in POLICY_PILLARS.keys()},
            "sector_linkage_counts": dict(policy_sectors_mapped),
        },
        "disambiguation_audit": {
            "sbv_pure_policy_maker": sbv_policy_maker_count,
            "sbv_with_commercial_banking": sbv_commercial_bank_count,
            "false_positive_avoidance_rate": round(sbv_policy_maker_count / (sbv_policy_maker_count + sbv_commercial_bank_count + 1e-6) * 100, 2),
        }
    }
    
    os.makedirs(os.path.dirname(OUT_REPORT), exist_ok=True)
    with open(OUT_REPORT, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
        
    print(f"\n[OK] Report saved to {OUT_REPORT}")


if __name__ == "__main__":
    run_preprocessing_audit()
