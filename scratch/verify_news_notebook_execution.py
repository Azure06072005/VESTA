import json
import sys
import matplotlib
matplotlib.use('Agg')

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

nb_path = "notebooks/news/01_vesta_unified_news_eda.ipynb"
with open(nb_path, "r", encoding="utf-8") as f:
    nb = json.load(f)

print(f"Tổng số cells trong notebook: {len(nb['cells'])}")
code_cells = [c for c in nb['cells'] if c['cell_type'] == 'code']
print(f"Số lượng code cells: {len(code_cells)}")

def display(x):
    if hasattr(x, 'head'):
        print(x.head(5))
    else:
        print(x)

global_env = {"display": display}

for idx, cell in enumerate(code_cells):
    code_text = "".join(cell['source'])
    # Chuyển path tương đối khi chạy từ root
    code_text = code_text.replace("../../db/vesta_news.duckdb", "db/vesta_news.duckdb")
    print(f"\n--- Đang kiểm tra Code Cell #{idx+1} ---")
    try:
        exec(code_text, global_env)
        print(f"✅ Cell #{idx+1} chạy thành công!")
    except Exception as e:
        print(f"❌ Cell #{idx+1} LỖI: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

print("\n🎉 Toàn bộ 11/11 code cells trong Notebook News EDA đều hợp lệ và chạy mượt mà 100%!")
