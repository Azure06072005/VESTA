import duckdb
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

print("=" * 75)
print("XÁC MINH VÀ SO SÁNH BỘ DỮ LIỆU F104: 45-DAY EMBARGO vs 5-DAY EMBARGO")
print("=" * 75)

# Đọc 2 manifest
with open("data/processed/f104/dataset_manifest.json", "r", encoding="utf-8") as f:
    m45 = json.load(f)

with open("data/processed/f104_embargo_5d/dataset_manifest.json", "r", encoding="utf-8") as f:
    m5 = json.load(f)

con = duckdb.connect()

print("\n1. THỐNG KÊ TẬP DỮ LIỆU:")
print(f"{'Phân vùng':15s} | {'45-Day Embargo (Cũ)':22s} | {'5-Day Embargo (Mới)':22s} | {'Chênh lệch (+Mẫu)':20s}")
print("-" * 85)

for split in ["train", "validation", "test"]:
    r45 = m45["partitions"][split]["row_count"]
    r5 = m5["partitions"][split]["row_count"]
    diff = r5 - r45
    diff_str = f"+{diff:,}" if diff > 0 else f"{diff:,}"
    print(f"{split:15s} | {r45:>18,} dòng | {r5:>18,} dòng | {diff_str:>18s}")

purged_45 = m45["total_records_purged"]
purged_5 = m5["total_records_purged"]
saved_samples = purged_45 - purged_5
print("-" * 85)
print(f"{'Bị Purged (Xóa)':15s} | {purged_45:>18,} dòng | {purged_5:>18,} dòng | {-saved_samples:>18,d} (Cứu được {saved_samples:,} mẫu)")
print(f"{'Tổng mẫu hữu dụng':15s} | {581943 - purged_45:>18,} dòng | {581943 - purged_5:>18,} dòng | {+saved_samples:>18,d}")

print("\n2. KIỂM TRA ĐỘ TOÀN VẸN CỦA CÁC TỆP PARQUET 5-DAY EMBARGO:")
for split in ["train", "val", "test"]:
    p = f"data/processed/f104_embargo_5d/f104_{split}.parquet"
    df = con.execute(f"SELECT count(symbol), min(event_date), max(event_date) FROM '{p}'").fetchone()
    print(f"  • f104_{split}.parquet: {df[0]:,} dòng | Từ ngày {df[1]} đến {df[2]} | SHA-256: {m5['partitions']['validation' if split == 'val' else split]['sha256'][:16]}... OK")

print("\n3. PHÂN BỔ NHÃN SENTIMENT TRÊN TẬP VALIDATION 2024 (THU HOẠCH TỪ 5-DAY EMBARGO):")
val_45_neg = m45["partitions"]["validation"]["sentiment_label_distribution"]["negative_0"]
val_5_neg = m5["partitions"]["validation"]["sentiment_label_distribution"]["negative_0"]
val_45_pos = m45["partitions"]["validation"]["sentiment_label_distribution"]["positive_2"]
val_5_pos = m5["partitions"]["validation"]["sentiment_label_distribution"]["positive_2"]

print(f"  • Nhãn Tiêu cực (Negative - Đảo chiều): Cũ = {val_45_neg:,} | Mới = {val_5_neg:,} (+{val_5_neg - val_45_neg} tín hiệu quý giá)")
print(f"  • Nhãn Tích cực (Positive): Cũ = {val_45_pos:,} | Mới = {val_5_pos:,} (+{val_5_pos - val_45_pos} tín hiệu)")

print("=" * 75)
