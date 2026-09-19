import sys
import pathlib
import time
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
print("Loading model on device:", device)

model = MultimodalCrossAttentionFusion(freeze_phobert_layers=8)
state = torch.load("out/models/multimodal_fusion/best_model.pt", map_location=device)
model.load_state_dict(state["model_state_dict"] if "model_state_dict" in state else state)
model.to(device).half().eval()

con = duckdb.connect()
# Test across 20,000 holdout test events
print("Loading holdout test events from data/processed/f104/f104_test.parquet...")
df = con.execute("SELECT * FROM 'data/processed/f104/f104_test.parquet' LIMIT 25000").df()
con.close()

print(f"Loaded {len(df):,} test events.")
tokenizer = AutoTokenizer.from_pretrained("vinai/phobert-base-v2")
ds = MultimodalFinancialDataset(df=df, tokenizer=tokenizer, max_seq_length=128)
loader = DataLoader(ds, batch_size=256, shuffle=False)

all_preds_return = []
all_preds_dir = []
all_preds_sent = []

t0 = time.time()
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

t1 = time.time()
print(f"Inference completed in {t1 - t0:.2f}s ({(len(df)/(t1-t0)):.0f} events/sec).")

df["pred_ret_t5"] = all_preds_return
df["pred_dir_t5"] = all_preds_dir  # 0: down, 1: flat, 2: up
df["pred_sent"] = all_preds_sent   # 0: neg, 1: neu, 2: pos

# Map to return_t5 and return_t30 from p0, p5, p30
df["return_t5"] = (df["p5"] - df["p0"]) / df["p0"]
df["return_t30"] = (df["p30"] - df["p0"]) / df["p0"]
df["published_at"] = pd.to_datetime(df["published_at"])
df["regime"] = df["published_at"].apply(assign_regime)

# Evaluate using predicted negative sentiment / predicted dip
# Compare:
# 1. Headline sentiment only (F201 baseline)
# 2. Multimodal Direction (dir == 0)
# 3. Multimodal Expected Return (pred_ret_t5 < -0.01)
# 4. Continuous Alpha Score S < 45

# Regime-dependent sigma for Continuous Alpha Score
sigma_thresh = 0.05
df["alpha_score"] = 50.0 + 50.0 * np.tanh(df["pred_ret_t5"] / sigma_thresh)

print("\n--- PERFORMANCE EVALUATION ON TEST SET ---")
# Strategy A: Predicted direction is down (dir == 0)
neg_dir = df[df["pred_dir_t5"] == 0]
res_dir = _paired_reversion_test(neg_dir)
print(f"[Direction Head (dir == 0)] n={res_dir.n:,}, mean_t5={res_dir.mean_return_t5:.4f}, mean_t30={res_dir.mean_return_t30:.4f}, t={res_dir.t_statistic:.4f}, p={res_dir.p_value:.2e}, Cohen's d={res_dir.cohens_d:.4f}")

# Strategy B: Predicted expected return is negative (pred_ret_t5 < -0.01)
neg_ret = df[df["pred_ret_t5"] < -0.01]
res_ret = _paired_reversion_test(neg_ret)
print(f"[Expected Return (E[R] < -1%)] n={res_ret.n:,}, mean_t5={res_ret.mean_return_t5:.4f}, mean_t30={res_ret.mean_return_t30:.4f}, t={res_ret.t_statistic:.4f}, p={res_ret.p_value:.2e}, Cohen's d={res_ret.cohens_d:.4f}")

# Strategy C: Continuous Alpha Score S < 40
neg_alpha = df[df["alpha_score"] < 40.0]
res_alpha = _paired_reversion_test(neg_alpha)
print(f"[Continuous Alpha Score (S < 40)] n={res_alpha.n:,}, mean_t5={res_alpha.mean_return_t5:.4f}, mean_t30={res_alpha.mean_return_t30:.4f}, t={res_alpha.t_statistic:.4f}, p={res_alpha.p_value:.2e}, Cohen's d={res_alpha.cohens_d:.4f}")

# Baseline: Cohen's d in F201 was 0.0557
print("\n--- BENCHMARK VS F201 BASELINE ---")
print(f"F201 Baseline Cohen's d: 0.0557")
print(f"F303 Multimodal Cohen's d (Direction): {res_dir.cohens_d:.4f} (Beat baseline? {res_dir.cohens_d > 0.0557})")
print(f"F303 Multimodal Cohen's d (Alpha Score S<40): {res_alpha.cohens_d:.4f} (Beat baseline? {res_alpha.cohens_d > 0.0557})")
