import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

FILE_PATH = "Harness/feature_list.json"

with open(FILE_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

features = data["features"]

# Tìm F100b
f100b_idx = None
f100b_item = None
for i, feat in enumerate(features):
    if feat["id"] == "F100b":
        f100b_idx = i
        f100b_item = feat
        break

if f100b_item is None:
    print("Không tìm thấy F100b!")
    sys.exit(1)

# Xóa F100b khỏi vị trí cũ
features.pop(f100b_idx)

# Cập nhật ID và dependencies của tính năng này thành F106 (cuối hàng đợi F1**)
f100b_item["id"] = "F106"
f100b_item["dependencies"] = ["F101", "F102", "F103", "F104", "F105"]
f100b_item["file_dependencies"] = [
    "notebooks/mapping/01_cross_lakehouse_data_mapping_eda.ipynb",
    "scratch/render_cross_lakehouse_mapping_eda.py",
    "scratch/audit_cross_lakehouse_mapping.py"
]

# Tìm vị trí F105
f105_idx = None
for i, feat in enumerate(features):
    if feat["id"] == "F105":
        f105_idx = i
        break

if f105_idx is None:
    print("Không tìm thấy F105!")
    sys.exit(1)

# Chèn vào ngay sau F105 (tức là cuối hàng đợi F1**, trước F201)
features.insert(f105_idx + 1, f100b_item)

with open(FILE_PATH, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("✅ Đã chuyển thành công tính năng mapping thành F106 và đưa vào cuối hàng đợi F1** (sau F105, trước F201)!")
