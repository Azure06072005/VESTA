import json

nb_path = "notebooks/ohlcv/01_ohlcv_1d_1m_sample_eda.ipynb"
with open(nb_path, "r", encoding="utf-8") as f:
    nb = json.load(f)

for cell in nb["cells"]:
    if cell["cell_type"] == "code":
        source_joined = "".join(cell["source"])
        if "../../db/vesta_snapshot.duckdb" in source_joined:
            new_source = []
            for line in cell["source"]:
                if "../../db/vesta_snapshot.duckdb" in line:
                    new_source.append(line.replace("../../db/vesta_snapshot.duckdb", "../../db/vesta_ohlcv.duckdb"))
                else:
                    new_source.append(line)
            cell["source"] = new_source
            print("Updated DB_PATH in notebook cell!")

with open(nb_path, "w", encoding="utf-8") as f:
    json.dump(nb, f, ensure_ascii=False, indent=1)

print("Saved updated notebook successfully!")
