import json
import sys
import matplotlib
matplotlib.use('Agg')

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

nb_path = "notebooks/ohlcv/02_market_indices_and_group_rooms_eda.ipynb"
with open(nb_path, "r", encoding="utf-8") as f:
    nb = json.load(f)

print(f"Tổng số cells trong notebook 02: {len(nb['cells'])}")
code_cells = [c for c in nb['cells'] if c['cell_type'] == 'code']
print(f"Số lượng code cells: {len(code_cells)}")

def display(x):
    print(x)

global_env = {"display": display}

for idx, cell in enumerate(code_cells):
    code_text = "".join(cell['source'])
    code_text = code_text.replace("../../db/vesta_ohlcv.duckdb", "db/vesta_ohlcv.duckdb")
    print(f"\n--- Đang kiểm tra Code Cell #{idx+1} ---")
    try:
        exec(code_text, global_env)
        print(f"✅ Cell #{idx+1} chạy thành công!")
    except Exception as e:
        print(f"❌ Cell #{idx+1} LỖI: {e}")
        sys.exit(1)

print("\n🎉 Toàn bộ code cells trong Notebook 02 EDA đều hợp lệ và chạy mượt mà!")
