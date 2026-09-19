import sys
import pathlib
import math
import numpy as np
import pandas as pd
import duckdb
import torch
from torch.utils.data import DataLoader
from transformers import AutoTokenizer

root_dir = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root_dir))
sys.path.insert(0, str(root_dir / "src"))

from models.multimodal_fusion import MultimodalCrossAttentionFusion, DEFAULT_FUNDAMENTAL_FEATURES
from models.train_multimodal_fusion import MultimodalFinancialDataset
from pipeline.backtest_meanreversion import _paired_reversion_test, REGIME_BOUNDARIES, assign_regime

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

model = MultimodalCrossAttentionFusion(freeze_phobert_layers=8)
state = torch.load("out/models/multimodal_fusion/best_model.pt", map_location=device)
model.load_state_dict(state["model_state_dict"] if "model_state_dict" in state else state)
model.to(device).half().eval()

con = duckdb.connect()
# Test across val set (which contains COVID, 2022 crisis, 2023 recovery) and test set
print("Loading val set (historical diverse regimes)...")
df_val = con.execute("SELECT * FROM 'data/processed/f104/f104_val.parquet' LIMIT 25000").df()
con.close()

tokenizer = AutoTokenizer.from_pretrained("vinai/phobert-base-v2")
ds = MultimodalFinancialDataset(df=df_val, tokenizer=tokenizer, max_seq_length=128)
loader = DataLoader(ds, batch_size=256, shuffle=False)

all_preds_return = []
all_preds_dir = []
all_preds_sent = []

with torch.no_grad():
    for b in loader:
        out = model(
            input_ids=b["input_ids"].to(device),
            attention_mask=b["attention_mask"].to(device),
            fundamentals=b["fundamentals"].to(device).half(),
            regime_ids=b["regime_id"].to(device)
        )
        all_preds_return.extend(out.return_preds.squeeze(-1).float().cpu().numpy())
        all_preds_dir.extend(out.direction_logits.argmax(dim=-1).cpu().numpy())
        all_preds_sent.extend(out.sentiment_logits.argmax(dim=-1).cpu().numpy())

df_val["pred_ret_t5"] = all_preds_return
df_val["pred_dir_t5"] = all_preds_dir
df_val["pred_sent"] = all_preds_sent

df_val["return_t5"] = (df_val["p5"] - df_val["p0"]) / df_val["p0"]
df_val["return_t30"] = (df_val["p30"] - df_val["p0"]) / df_val["p0"]
df_val["published_at"] = pd.to_datetime(df_val["published_at"])
df_val["regime"] = df_val["published_at"].apply(assign_regime)

sigma_thresh = 0.05
df_val["alpha_score"] = 50.0 + 50.0 * np.tanh(df_val["pred_ret_t5"] / sigma_thresh)

print("\n--- THRESHOLD SWEEP ON VALIDATION SET ---")
for thresh in [45, 40, 35, 30, 25, 20, 15]:
    sub = df_val[df_val["alpha_score"] < thresh]
    res = _paired_reversion_test(sub)
    if res.status == "ok":
        print(f"Alpha S < {thresh:2d}: n={res.n:5,d}, mean_diff={res.mean_return_t30 - res.mean_return_t5:+.4f}, t={res.t_statistic:6.3f}, p={res.p_value:.2e}, Cohen's d={res.cohens_d:.4f}")
    else:
        print(f"Alpha S < {thresh:2d}: n={res.n} (insufficient)")

# Also test Multimodal Sentiment Head (pred_sent == 0)
sub_sent = df_val[df_val["pred_sent"] == 0]
res_sent = _paired_reversion_test(sub_sent)
print(f"\nMultimodal Sentiment Head (Negative): n={res_sent.n}, mean_diff={res_sent.mean_return_t30 - res_sent.mean_return_t5:+.4f}, Cohen's d={res_sent.cohens_d:.4f}")
