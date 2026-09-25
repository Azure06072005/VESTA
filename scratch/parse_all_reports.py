import os
import re
import json

progress_dir = "d:/VESTA/Progress Report"
files = [
    "00_MASTER_EXECUTIVE_SUMMARY.md",
    "01_TIER_F0XX_CORE_DATA_CRAWLERS.md",
    "02_TIER_F05X_AUXILIARY_MACRO_CRAWLERS.md",
    "03_F1XX_REPROCESSING_SESSION_EDA_REPORT.md",
    "03_TIER_F1XX_DATA_INTEGRITY_PIT_FEATURES.md",
    "04_TIER_F2XX_STATISTICAL_HYPOTHESIS_GATES.md",
    "05_TIER_F3XX_NLP_MULTIMODAL_CONSISTENCY.md",
    "06_TIER_F4XX_F9XX_PRODUCTION_EXECUTION_COMPLIANCE.md",
    "07_TIER_F5XX_MONTE_CARLO_BOT_ARENA.md"
]

all_reviews = {}

for fname in files:
    fpath = os.path.join(progress_dir, fname)
    if not os.path.exists(fpath):
        continue
    with open(fpath, "r", encoding="utf-8") as f:
        text = f.read()
    
    # Split by headers
    sections = re.split(r'\n(?=#{1,4}\s)', text)
    extracted = []
    for sec in sections:
        header = sec.split('\n')[0].strip()
        header_lower = header.lower()
        if any(k in header_lower for k in ["ưu điểm", "nhược điểm", "hạn chế", "điểm yếu", "swot", "đề xuất", "khoảng trống", "pros & cons", "recommended"]):
            extracted.append({
                "header": header,
                "content": sec.strip()
            })
    all_reviews[fname] = extracted

with open("scratch/all_reports_pros_cons.json", "w", encoding="utf-8") as f:
    json.dump(all_reviews, f, ensure_ascii=False, indent=2)

print(f"Extracted {sum(len(v) for v in all_reviews.values())} sections across {len(all_reviews)} reports.")
