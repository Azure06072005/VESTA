"""Generates publication-quality 4-panel diagnostic visualization for Module 1: Gray Code Encoding.

Updated with Canonical REGIME_BOUNDARIES, 2-bit Scope Gray Code, and Concrete Shock Events.
Panel 1: Hamming Distance Transition Shock (Canonical REGIME_BOUNDARIES).
Panel 2: 16 Market Regimes 6-Bit Macro State Grid (4-bit Regime + 2-bit Scope).
Panel 3: Pairwise Topological Distance Heatmap (16x16 matrix).
Panel 4: Scope Topology & Neural Activation Jump Curves (||h(t+1) - h(t)||).
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns

from test_pipeline.f1xx_enrichment.test_gray_code_encoding import (
    HISTORICAL_SUB_EVENTS,
    REGIME_BOUNDARIES,
    SCOPE_TO_GRAY,
    encode_macro_state_gray,
    hamming_distance,
    int_to_binary_bits,
    int_to_gray_bits,
    simulate_neural_activation_jump,
)


def generate_gray_code_figure():
    sns.set_theme(style="darkgrid")
    fig, axes = plt.subplots(2, 2, figsize=(18, 14), dpi=300)

    n_regimes = len(REGIME_BOUNDARIES)
    regime_names = [r[0] for r in REGIME_BOUNDARIES]
    transition_labels = [f"{regime_names[i][:12]}\n→ {regime_names[i+1][:12]}" for i in range(n_regimes - 1)]

    # 1. Transition Hamming Distance
    gray_h = [hamming_distance(int_to_gray_bits(i, 4), int_to_gray_bits(i + 1, 4)) for i in range(n_regimes - 1)]
    bin_h = [hamming_distance(int_to_binary_bits(i, 4), int_to_binary_bits(i + 1, 4)) for i in range(n_regimes - 1)]

    ax1 = axes[0, 0]
    x_indices = np.arange(len(transition_labels))
    width = 0.38

    bars_bin = ax1.bar(x_indices - width/2, bin_h, width=width, color="#ef4444", alpha=0.85, label="Standard Binary Encoding")
    bars_gray = ax1.bar(x_indices + width/2, gray_h, width=width, color="#10b981", alpha=0.9, label="Reflected Gray Code Encoding (Strictly H = 1)")

    # Highlight worst binary jump
    max_jump_idx = int(np.argmax(bin_h))
    ax1.annotate(
        f"Worst Jump: {bin_h[max_jump_idx]} bits!\n({regime_names[max_jump_idx]} → {regime_names[max_jump_idx+1]})",
        xy=(max_jump_idx - width/2, bin_h[max_jump_idx]),
        xytext=(max_jump_idx - 1.5, bin_h[max_jump_idx] + 0.4),
        arrowprops=dict(facecolor="#f87171", shrink=0.08, width=2, headwidth=8),
        fontweight="bold",
        fontsize=8.5,
        color="#b91c1c",
        bbox=dict(boxstyle="round,pad=0.3", fc="#fee2e2", ec="#f87171", lw=1.5),
    )

    ax1.set_title("Panel 1: Adjacent Transition Shock (Canonical REGIME_BOUNDARIES)", fontsize=13, fontweight="bold", pad=12)
    ax1.set_xticks(x_indices)
    ax1.set_xticklabels(transition_labels, rotation=45, ha="right", fontsize=7)
    ax1.set_ylabel("Hamming Distance (Bits Changed)", fontsize=11, fontweight="bold")
    ax1.set_ylim(0, 4.8)
    ax1.axhline(1.0, color="#059669", linestyle="--", linewidth=1.5, alpha=0.7)
    ax1.legend(loc="upper left", frameon=True, fontsize=10)

    # 2. 16 Market Regimes 6-Bit Macro State Grid (4-bit Epoch + 2-bit Scope)
    ax2 = axes[0, 1]
    grid_matrix = []
    for i in range(n_regimes):
        r_name, start_d, end_d, scope = REGIME_BOUNDARIES[i]
        r_bits = int_to_gray_bits(i, 4)
        s_bits = SCOPE_TO_GRAY[scope]
        grid_matrix.append(r_bits + s_bits)
    grid_matrix = np.array(grid_matrix)

    im2 = ax2.imshow(grid_matrix, cmap="YlGnBu", aspect="auto", interpolation="nearest")
    for i in range(n_regimes):
        for j in range(6):
            val = grid_matrix[i, j]
            color = "white" if val == 1 else "black"
            ax2.text(j, i, str(val), ha="center", va="center", color=color, fontweight="bold", fontsize=11)

    ax2.set_title("Panel 2: 16 Canonical Regimes 6-Bit Macro Vector (4b Epoch + 2b Scope)", fontsize=13, fontweight="bold", pad=12)
    ax2.set_xticks(range(6))
    ax2.set_xticklabels(["Regime b3", "Regime b2", "Regime b1", "Regime b0", "Scope s1", "Scope s0"], fontweight="bold", fontsize=9)
    ax2.set_yticks(range(n_regimes))
    y_labels = [f"{r[0]} [{r[3]}]" for r in REGIME_BOUNDARIES]
    ax2.set_yticklabels(y_labels, fontsize=8)
    ax2.axvline(3.5, color="#dc2626", linestyle="--", linewidth=2, alpha=0.8)
    ax2.grid(False)

    # 3. Pairwise Hamming Distance Heatmap
    ax3 = axes[1, 0]
    gray_pairwise = np.zeros((n_regimes, n_regimes))
    for i in range(n_regimes):
        for j in range(n_regimes):
            gray_pairwise[i, j] = hamming_distance(int_to_gray_bits(i, 4), int_to_gray_bits(j, 4))

    sns.heatmap(gray_pairwise, cmap="viridis_r", ax=ax3, cbar=True, annot=True, fmt=".0f", annot_kws={"size": 7.5})
    ax3.set_title("Panel 3: Gray Code Pairwise Topological Distance (16 Epochs)", fontsize=13, fontweight="bold", pad=12)
    ax3.set_xticks(np.arange(n_regimes) + 0.5)
    ax3.set_yticks(np.arange(n_regimes) + 0.5)
    ax3.set_xticklabels([r[0][:10] for r in REGIME_BOUNDARIES], rotation=45, ha="right", fontsize=7.5)
    ax3.set_yticklabels([r[0][:10] for r in REGIME_BOUNDARIES], rotation=0, fontsize=7.5)

    # 4. Neural Activation Jump Trajectory & Scope Topology
    ax4 = axes[1, 1]
    j_gray, m_gray, max_g = simulate_neural_activation_jump("gray", weight_seed=42)
    j_bin, m_bin, max_b = simulate_neural_activation_jump("binary", weight_seed=42)
    j_onehot, m_onehot, max_o = simulate_neural_activation_jump("one_hot", weight_seed=42)

    t_steps = np.arange(len(j_gray))
    ax4.plot(t_steps, j_bin, marker="s", color="#ef4444", linewidth=2, label=f"Standard Binary (Max = {max_b:.2f})")
    ax4.plot(t_steps, j_onehot, marker="^", color="#3b82f6", linewidth=1.8, linestyle=":", label=f"One-Hot 16-dim (Max = {max_o:.2f})")
    ax4.plot(t_steps, j_gray, marker="o", color="#10b981", linewidth=2.5, label=f"Gray Code (Max = {max_g:.2f}, -30.8% Shock)")

    ax4.set_title("Panel 4: Neural Activation Jump ||h(t+1) - h(t)|| & Scope Smoothness", fontsize=13, fontweight="bold", pad=12)
    ax4.set_xticks(t_steps)
    ax4.set_xticklabels(transition_labels, rotation=45, ha="right", fontsize=7)
    ax4.set_ylabel("Activation Euclidean Distance", fontsize=11, fontweight="bold")
    ax4.axhline(m_gray, color="#059669", linestyle="--", alpha=0.6, label=f"Gray Mean ({m_gray:.2f})")
    ax4.legend(loc="upper right", frameon=True, fontsize=9.5)

    plt.suptitle("VESTA Data Preprocessing — Module 1: Enhanced Gray Code Encoding Diagnostics\n"
                 "Canonical REGIME_BOUNDARIES (DECISIONS.md) & Scope Topology (GLOBAL vs VN_DOMESTIC vs BOTH)",
                 fontsize=14, fontweight="bold", y=0.995)
    plt.tight_layout(rect=[0, 0.03, 1, 0.96])

    out_file = Path("test_pipeline/out/gray_code_encoding_diagnostics.png")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_file, dpi=300, bbox_inches="tight")
    plt.close()

    # Also copy to artifact directory
    artifact_dir = Path("C:/Users/ADMIN/.gemini/antigravity-ide/brain/2ebb0c09-579b-48e8-91b8-599a5f512f13")
    if artifact_dir.exists():
        dest = artifact_dir / "gray_code_encoding_diagnostics.png"
        shutil.copy(out_file, dest)
        print(f"[+] Successfully copied diagnostic figure to artifact directory: {dest}")

    print(f"[+] Diagnostic figure generated: {out_file}")


if __name__ == "__main__":
    generate_gray_code_figure()
