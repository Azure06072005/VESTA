import json
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

nb_path = "notebooks/news/02_news_fundamental_entity_mapping_eda.ipynb"
with open(nb_path, "r", encoding="utf-8") as f:
    nb = json.load(f)

print(f"Tổng số cell: {len(nb['cells'])}")
for i, cell in enumerate(nb['cells']):
    ctype = cell['cell_type']
    source = "".join(cell['source'])[:120].replace("\n", " ")
    has_outputs = len(cell.get('outputs', []))
    print(f"[{i:02d}] {ctype:8s} | outputs: {has_outputs:2d} | {source}...")
