import sys
import pathlib
import torch
import numpy as np
import pandas as pd
import duckdb

root_dir = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root_dir))
sys.path.insert(0, str(root_dir / "src"))

from models.multimodal_fusion import MultimodalCrossAttentionFusion, DEFAULT_FUNDAMENTAL_FEATURES

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model = MultimodalCrossAttentionFusion(freeze_phobert_layers=8)
state = torch.load("out/models/multimodal_fusion/best_model.pt", map_location=device)
model.load_state_dict(state["model_state_dict"] if "model_state_dict" in state else state)
model.to(device).eval()

# 1. Weight Norm Importance (Projection Layer Weight Norms)
# Each column i of fundamental_proj.weight corresponds to feature i
W_fund = model.fundamental_projection[0].weight.detach().cpu()  # [hidden_dim, 24]
fund_norms = torch.norm(W_fund, dim=0).numpy()

# 2. Macro Regime Embedding Norms
W_regime = model.regime_embedding.weight.detach().cpu()
regime_norms = torch.norm(W_regime, dim=1).numpy()
regime_names = ["BULL", "BEAR", "CRISIS_HIGH_VOL", "SIDEWAYS"]

# 3. Dynamic Feature Sensitivity (Gradient Salience on Val Batch)
con = duckdb.connect()
df_sample = con.execute("SELECT * FROM 'data/processed/f104/f104_val.parquet' LIMIT 2000").df()
con.close()

from transformers import AutoTokenizer
from models.train_multimodal_fusion import MultimodalFinancialDataset
from torch.utils.data import DataLoader

tokenizer = AutoTokenizer.from_pretrained("vinai/phobert-base-v2")
ds = MultimodalFinancialDataset(df=df_sample, tokenizer=tokenizer, max_seq_length=128)
loader = DataLoader(ds, batch_size=128, shuffle=False)

salience = torch.zeros(len(DEFAULT_FUNDAMENTAL_FEATURES), device=device)
total_count = 0

for b in loader:
    fund_tensor = b["fundamentals"].to(device).requires_grad_(True)
    out = model(
        input_ids=b["input_ids"].to(device),
        attention_mask=b["attention_mask"].to(device),
        fundamentals=fund_tensor,
        regime_ids=b["regime_id"].to(device)
    )
    # Target: Return predictions
    loss = out.return_preds.sum()
    loss.backward()
    with torch.no_grad():
        salience += fund_tensor.grad.abs().sum(dim=0)
        total_count += len(fund_tensor)

mean_salience = (salience / total_count).cpu().numpy()

results = []
for i, name in enumerate(DEFAULT_FUNDAMENTAL_FEATURES):
    results.append({
        "feature": name,
        "weight_norm": float(fund_norms[i]),
        "gradient_salience": float(mean_salience[i]),
        "combined_rank_score": float(fund_norms[i] * mean_salience[i])
    })

df_importance = pd.DataFrame(results).sort_values(by="combined_rank_score", ascending=False)
print("=" * 80)
print("FEATURE IMPORTANCE RANKING (Multimodal Model F302)")
print("=" * 80)
print(df_importance.to_string(index=False))

print("\n--- MACRO REGIME EMBEDDING NORMS ---")
for name, norm in zip(regime_names, regime_norms):
    print(f" - {name:16s}: norm={norm:.4f}")
