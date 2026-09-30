import json
import sys
import matplotlib
matplotlib.use('Agg')

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

with open("notebooks/ohlcv/01_ohlcv_1d_1m_sample_eda.ipynb", "r", encoding="utf-8") as f:
    nb = json.load(f)

print(f"Tổng số cells trong notebook: {len(nb['cells'])}")
code_cells = [c for c in nb['cells'] if c['cell_type'] == 'code']
print(f"Số lượng code cells: {len(code_cells)}")

# Mock display nếu chạy ngoài jupyter
def display(x):
    print(x)

global_env = {"display": display}

# Đổi đường dẫn tương đối DB khi test từ root directory
for idx, cell in enumerate(code_cells):
    code_text = "".join(cell['source'])
    # Nếu chạy từ d:\VESTA thì DB_PATH là db/vesta_ohlcv.duckdb
    code_text = code_text.replace("../../db/vesta_ohlcv.duckdb", "db/vesta_ohlcv.duckdb")
    code_text = code_text.replace("../../db/vesta_snapshot.duckdb", "db/vesta_snapshot.duckdb")
    print(f"\n--- Đang kiểm tra Code Cell #{idx+1} ---")
    try:
        exec(code_text, global_env)
        print(f"✅ Cell #{idx+1} chạy thành công!")
    except Exception as e:
        print(f"❌ Cell #{idx+1} LỖI: {e}")
        sys.exit(1)

print("\n🎉 Toàn bộ code cells trong Notebook EDA đều hợp lệ và chạy mượt mà!")
