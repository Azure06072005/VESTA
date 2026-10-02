import base64
import io
import json
import sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

nb_path = "notebooks/fundamentals/01_vesta_fundamentals_snapshot_eda.ipynb"
with open(nb_path, "r", encoding="utf-8") as f:
    nb = json.load(f)

print(f"Tổng số cells: {len(nb['cells'])}", flush=True)
code_indices = [i for i, c in enumerate(nb['cells']) if c['cell_type'] == 'code']
print(f"Số lượng code cells cần render: {len(code_indices)}", flush=True)

# Môi trường thực thi
global_env = {}

def execute_and_capture(code_text, step_num):
    captured_outputs = []
    old_stdout = sys.stdout
    buf = io.StringIO()
    sys.stdout = buf

    # Custom display handler
    def custom_display(obj):
        if hasattr(obj, 'to_html'):
            captured_outputs.append({
                "data": {
                    "text/html": [obj.to_html() + "\n"],
                    "text/plain": [str(obj) + "\n"]
                },
                "metadata": {},
                "output_type": "display_data"
            })
        else:
            print(obj)

    # Custom plt.show handler
    def custom_show():
        fig = plt.gcf()
        if fig.get_axes():
            img_buf = io.BytesIO()
            fig.savefig(img_buf, format='png', bbox_inches='tight', dpi=120)
            img_buf.seek(0)
            b64_data = base64.b64encode(img_buf.read()).decode('utf-8')
            captured_outputs.append({
                "data": {
                    "image/png": b64_data,
                    "text/plain": ["<Figure size ...>\n"]
                },
                "metadata": {},
                "output_type": "display_data"
            })
            plt.close(fig)

    global_env['display'] = custom_display
    global_env['plt'].show = custom_show

    try:
        exec(code_text, global_env)
    finally:
        sys.stdout = old_stdout

    std_val = buf.getvalue()
    if std_val:
        captured_outputs.insert(0, {
            "name": "stdout",
            "output_type": "stream",
            "text": [line + "\n" for line in std_val.splitlines()]
        })

    return captured_outputs

# Setup initial global env
import duckdb
import numpy as np
import pandas as pd
global_env['duckdb'] = duckdb
global_env['np'] = np
global_env['pd'] = pd
global_env['plt'] = plt

for step_num, cell_idx in enumerate(code_indices):
    cell = nb['cells'][cell_idx]
    code_text = "".join(cell['source'])
    print(f"--- Đang thực thi và render Cell #{step_num+1} (Cell index {cell_idx}) ---", flush=True)
    outputs = execute_and_capture(code_text, step_num+1)
    cell['outputs'] = outputs
    cell['execution_count'] = step_num + 1
    print(f"✅ Render Cell #{step_num+1} thành công với {len(outputs)} outputs!", flush=True)

with open(nb_path, "w", encoding="utf-8") as f:
    json.dump(nb, f, indent=2, ensure_ascii=False)

print(f"\n🎉 Toàn bộ {len(code_indices)} code cells đã được thực thi và nhúng hình ảnh/bảng biểu hoàn tất!", flush=True)
print(f"💾 File notebook đã cập nhật: {nb_path}", flush=True)
