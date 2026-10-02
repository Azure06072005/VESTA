import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open("Harness/feature_list.json", "r", encoding="utf-8") as f:
    data = json.load(f)

# Kiểm tra xem F100b đã có chưa
existing_ids = [feat["id"] for feat in data["features"]]
if "F100b" in existing_ids:
    print("F100b đã tồn tại trong feature_list.json!")
    sys.exit(0)

f100b = {
    "id": "F100b",
    "name": "Cross-lakehouse relational entity mapping & comprehensive data linkage EDA suite",
    "behavior": "Comprehensive quantitative profiling and entity-relationship mapping suite across all three core VESTA lakehouses (vesta_snapshot.duckdb, vesta_ohlcv.duckdb, and vesta_news.duckdb): (1) Universal Master ERD Matrix: Establishing explicit Primary Key / Foreign Key graph linkages centered on core.dim_symbol (1,751 active tickers). (2) Intra-Snapshot Referential Integrity Audit: Verifying 100% join coverage across 35 tables (Financials, Financial Notes, Major Shareholders, Executives, Corporate Events, Foreign Flows, Factor Screener). (3) Snapshot-to-OHLCV Dimensional Alignment: Verifying 99.3% ticker match rate spanning 5.18M daily bars and 22.75M 1-minute microstructure bars. (4) News-to-Fundamental Entity Resolution Audit: Deep mapping of 1.15M news articles via direct ticker tagging (590k matches), corporate executive/shareholder names in body text (F105 gate), and ICB industry signals. (5) Cross-Lakehouse Join Match Rate KPI Card & Pre-F101 Validation Firewall. Realized in notebooks/mapping/01_cross_lakehouse_data_mapping_eda.ipynb.",
    "dependencies": [
        "F099",
        "F099b",
        "F100",
        "F105"
    ],
    "verification": "python scratch/render_cross_lakehouse_mapping_eda.py",
    "state": "active",
    "evidence": "Under construction: Deep research notebook notebooks/mapping/01_cross_lakehouse_data_mapping_eda.ipynb mapping relational integrity across all 3 databases.",
    "pros": [
        "Eliminates Data Silos: Explicitly connects financial statements, market microstructure, ownership hierarchies, and textual news into a cohesive relational knowledge graph.",
        "Guarantees Clean Join Semantics: Prevents catastrophic silent data loss or cross-join row explosion before launching the automated PIT Join Engine (F102)."
    ],
    "cons": [
        "Cross-database multi-table JOINs require attaching 3 DuckDB files simultaneously, necessitating memory-conscious projection queries."
    ],
    "recommendation": [
        "Use explicit column projections (avoid SELECT *) and utilize DuckDB ATTACH (READ_ONLY) to maximize cross-database I/O throughput."
    ],
    "file_dependencies": [
        "notebooks/mapping/01_cross_lakehouse_data_mapping_eda.ipynb"
    ]
}

# Chèn F100b ngay sau F100
new_features = []
for feat in data["features"]:
    new_features.append(feat)
    if feat["id"] == "F100":
        new_features.append(f100b)

data["features"] = new_features

with open("Harness/feature_list.json", "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print(f"✅ Đã chèn thành công F100b vào Harness/feature_list.json! Tổng số features: {len(data['features'])}")
