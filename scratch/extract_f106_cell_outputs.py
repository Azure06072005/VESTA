import json
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

nb_path = "notebooks/mapping/01_cross_lakehouse_data_mapping_eda.ipynb"
with open(nb_path, "r", encoding="utf-8") as f:
    nb = json.load(f)

for idx in [1, 3, 5, 7, 9, 10]:
    cell = nb['cells'][idx]
    print("=" * 80)
    print(f"CELL {idx} ({cell['cell_type']}):")
    if cell['cell_type'] == 'markdown':
        print("".join(cell['source']))
    else:
        for out in cell.get('outputs', []):
            if out.get('output_type') == 'stream':
                print("".join(out.get('text', [])))
            elif out.get('output_type') == 'display_data':
                text_data = out.get('data', {}).get('text/plain', [])
                print("".join(text_data))
