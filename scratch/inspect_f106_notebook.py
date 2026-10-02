import json
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

nb_path = "notebooks/mapping/01_cross_lakehouse_data_mapping_eda.ipynb"
with open(nb_path, "r", encoding="utf-8") as f:
    nb = json.load(f)

print(f"Tổng số cell: {len(nb['cells'])}")
for i, cell in enumerate(nb['cells']):
    ctype = cell['cell_type']
    source = "".join(cell.get('source', []))[:100].replace("\n", " ")
    out_cnt = len(cell.get('outputs', []))
    print(f"[{i:02d}] {ctype:8s} | outputs: {out_cnt:2d} | {source}...")
