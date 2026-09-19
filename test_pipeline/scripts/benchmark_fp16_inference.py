import sys
import pathlib
import time
import torch
import duckdb
from torch.utils.data import DataLoader
from transformers import AutoTokenizer

root_dir = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root_dir))
sys.path.insert(0, str(root_dir / "src"))

from models.multimodal_fusion import MultimodalCrossAttentionFusion, DEFAULT_FUNDAMENTAL_FEATURES
from models.train_multimodal_fusion import MultimodalFinancialDataset

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model = MultimodalCrossAttentionFusion(freeze_phobert_layers=8)
state = torch.load("out/models/multimodal_fusion/best_model.pt", map_location=device)
model.load_state_dict(state["model_state_dict"] if "model_state_dict" in state else state)
model.to(device).half().eval()

con = duckdb.connect()
df = con.execute("SELECT * FROM 'data/processed/f104/f104_test.parquet' LIMIT 5000").df()
con.close()

tokenizer = AutoTokenizer.from_pretrained("vinai/phobert-base-v2")
ds = MultimodalFinancialDataset(df=df, tokenizer=tokenizer, max_seq_length=128)
loader = DataLoader(ds, batch_size=256, shuffle=False)

t0 = time.time()
with torch.no_grad():
    for b in loader:
        out = model(
            input_ids=b["input_ids"].to(device),
            attention_mask=b["attention_mask"].to(device),
            fundamentals=b["fundamentals"].to(device).half(),
            regime_ids=b["regime_id"].to(device)
        )
t1 = time.time()
print(f"FP16 inference on 5,000 samples: {t1-t0:.2f}s ({(5000/(t1-t0)):.0f} samples/sec)")
print("Peak VRAM:", torch.cuda.max_memory_allocated() / 1e9, "GB")
