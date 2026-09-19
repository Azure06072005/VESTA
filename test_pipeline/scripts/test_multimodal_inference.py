import sys
import pathlib
root_dir = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root_dir))
sys.path.insert(0, str(root_dir / "src"))

import time
import pandas as pd
import torch
import duckdb
from transformers import AutoTokenizer
from models.multimodal_fusion import MultimodalCrossAttentionFusion, DEFAULT_FUNDAMENTAL_FEATURES
from models.train_multimodal_fusion import MultimodalFinancialDataset
from torch.utils.data import DataLoader

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print("Device:", device)

model = MultimodalCrossAttentionFusion(
    phobert_model_name="vinai/phobert-base-v2",
    freeze_phobert_layers=8,
    num_fundamental_features=len(DEFAULT_FUNDAMENTAL_FEATURES),
    hidden_dim=128,
    num_heads=4,
    num_fusion_layers=2,
)
state = torch.load("out/models/multimodal_fusion/best_model.pt", map_location=device)
if "model_state_dict" in state:
    model.load_state_dict(state["model_state_dict"])
else:
    model.load_state_dict(state)
model.to(device)
model.eval()
print("Model loaded successfully.")

con = duckdb.connect()
df_sample = con.execute("SELECT * FROM 'data/processed/f104/f104_test.parquet' LIMIT 1000").df()
con.close()

tokenizer = AutoTokenizer.from_pretrained("vinai/phobert-base-v2")
ds = MultimodalFinancialDataset(df=df_sample, tokenizer=tokenizer, max_seq_length=128)
loader = DataLoader(ds, batch_size=128, shuffle=False)

t0 = time.time()
all_returns = []
all_dirs = []
all_sents = []

with torch.no_grad():
    for batch in loader:
        input_ids = batch["input_ids"].to(device)
        attn_mask = batch["attention_mask"].to(device)
        fund = batch["fundamentals"].to(device)
        regime = batch["regime_id"].to(device)
        out = model(input_ids=input_ids, attention_mask=attn_mask, fundamentals=fund, regime_ids=regime)
        all_sents.extend(out.sentiment_logits.argmax(dim=-1).cpu().tolist())
        all_dirs.extend(out.direction_logits.argmax(dim=-1).cpu().tolist())
        all_returns.extend(out.return_preds.squeeze(-1).cpu().tolist())

t1 = time.time()
print(f"Scored 1,000 samples in {t1 - t0:.2f}s ({(1000 / (t1 - t0)):.0f} samples/sec)")
print("Sentiment counts:", pd.Series(all_sents).value_counts().to_dict())
print("Direction counts (0:down, 1:flat, 2:up):", pd.Series(all_dirs).value_counts().to_dict())
print("Expected Return summary: mean =", sum(all_returns)/len(all_returns), "min =", min(all_returns), "max =", max(all_returns))
