"""test_pipeline/scripts/generate_text_preprocessing_visualizations.py

Generates 4-panel diagnostic dashboard for Step 5: Text Preprocessing, Deduplication & Entity Disambiguation.
Visualizes:
1. Macro Policy Taxonomy & Pillar Breakdown (Monetary, Fiscal, Real Estate, Capital Markets, etc.)
2. Corpus Deduplication Rate (Canonical vs Exact Duplicates vs Syndicated Near-Duplicates)
3. Entity Disambiguation Precision: SBV as Regulatory Policy Maker vs. Commercial Bank Sector 11
4. Macro-to-Sector Transmission Mapping Matrix (Number of policies influencing each stock sector)
"""
from __future__ import annotations

import json
import os
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

REPORT_JSON = "test_pipeline/out/text_preprocessing_report.json"
OUT_PNG_PIPELINE = "test_pipeline/out/text_preprocessing_diagnostics.png"
ARTIFACT_DIR = "C:/Users/ADMIN/.gemini/antigravity-ide/brain/2ebb0c09-579b-48e8-91b8-599a5f512f13"
OUT_PNG_ARTIFACT = os.path.join(ARTIFACT_DIR, "text_preprocessing_diagnostics.png")


def generate_visualizations():
    print("Generating Text Preprocessing Visual Diagnostics Dashboard...")
    with open(REPORT_JSON, "r", encoding="utf-8") as f:
        report = json.load(f)
        
    fig = plt.figure(figsize=(18, 12), dpi=300)
    plt.subplots_adjust(hspace=0.35, wspace=0.25)
    
    # ----------------------------------------------------
    # Panel 1: Macro Policy Taxonomy Breakdown
    # ----------------------------------------------------
    ax1 = fig.add_subplot(2, 2, 1)
    pillars = report["macro_policy_classification"]["pillar_breakdown"]
    
    pillar_labels = [
        "Tài khóa & Đầu tư công\n(Fiscal / Infra)",
        "Thị trường Chứng khoán\n(Capital Markets)",
        "Tiền tệ & Lãi suất\n(Monetary Policy)",
        "Bất động sản & TPDN\n(Real Estate & Bonds)",
        "Tin DN bị lẫn\n(Misrouted Corporate)",
        "Năng lượng & Ngoại thương\n(Energy & Trade)"
    ]
    pillar_vals = [
        pillars["FISCAL_INFRASTRUCTURE"],
        pillars["CAPITAL_MARKETS"],
        pillars["MONETARY"],
        pillars["REAL_ESTATE_BONDS"],
        pillars["MISROUTED_CORPORATE"],
        pillars["ENERGY_TRADE"],
    ]
    colors1 = ["#1f77b4", "#9467bd", "#2ca02c", "#ff7f0e", "#d62728", "#17becf"]
    
    bars1 = ax1.barh(pillar_labels, pillar_vals, color=colors1, alpha=0.85, edgecolor="black")
    for b, val in zip(bars1, pillar_vals):
        ax1.text(b.get_width() + 3, b.get_y() + b.get_height()/2, f"{val} ({val/5000*100:.1f}%)", 
                 va="center", fontsize=9, fontweight="bold")
                 
    ax1.set_title("Panel 1: Macro Policy Taxonomy & Core Pillars\nClassification of 5,000 Sampled Administrative Documents", fontsize=12, fontweight="bold")
    ax1.set_xlabel("Number of Documents", fontsize=10)
    ax1.set_xlim(0, max(pillar_vals) * 1.25)
    ax1.grid(True, alpha=0.3, axis="x")
    ax1.invert_yaxis()

    # ----------------------------------------------------
    # Panel 2: Corpus Deduplication Breakdown
    # ----------------------------------------------------
    ax2 = fig.add_subplot(2, 2, 2)
    exact_dups = report["deduplication"]["exact_duplicate_count"]
    total_docs = report["sample_size"]["total_documents"]
    unique_canonical = total_docs - exact_dups
    
    sizes = [unique_canonical, exact_dups]
    labels_pie = [f"Bản gốc chuẩn hóa (Canonical)\n{unique_canonical:,} bài ({unique_canonical/total_docs*100:.1f}%)",
                  f"Bản sao trùng lặp 100% (Exact Dups)\n{exact_dups:,} bài ({exact_dups/total_docs*100:.1f}%)"]
    colors_pie = ["#2ca02c", "#d62728"]
    
    wedges, texts, autotexts = ax2.pie(sizes, labels=labels_pie, autopct="%1.1f%%",
                                       startangle=140, colors=colors_pie, explode=(0, 0.08),
                                       textprops=dict(fontsize=9, fontweight="bold"))
    for at in autotexts:
        at.set_color("white")
        at.set_fontsize(11)
        
    ax2.set_title("Panel 2: MinHash LSH Corpus Deduplication\n13.21% of Articles are Byte-for-Byte Redundant Syndications", fontsize=12, fontweight="bold")

    # ----------------------------------------------------
    # Panel 3: Entity Disambiguation: SBV Policy Maker vs Banking Sector
    # ----------------------------------------------------
    ax3 = fig.add_subplot(2, 2, 3)
    sbv_pure = report["disambiguation_audit"]["sbv_pure_policy_maker"]
    sbv_comm = report["disambiguation_audit"]["sbv_with_commercial_banking"]
    avoid_rate = report["disambiguation_audit"]["false_positive_avoidance_rate"]
    
    cats = ["Chính sách Hành chính SBV\n(Lọc bỏ: Không gán Ngân hàng)",
            "Chính sách Vận hành Tín dụng\n(Được gán Ngành Ngân hàng - 11)"]
    vals3 = [sbv_pure, sbv_comm]
    colors3 = ["#2ca02c", "#1f77b4"]
    
    bars3 = ax3.bar(cats, vals3, color=colors3, width=0.45, alpha=0.85, edgecolor="black")
    for b, val in zip(bars3, vals3):
        ax3.text(b.get_x() + b.get_width()/2, b.get_height() + 0.8, f"{val} bài ({val/(sbv_pure+sbv_comm)*100:.1f}%)", 
                 ha="center", va="bottom", fontsize=10, fontweight="bold")
                 
    ax3.set_title(f"Panel 3: Entity Disambiguation Precision (NHNN vs Ngân hàng)\nKhử Nhiễu Báo Động Giả Đạt {avoid_rate}% (66.7% SBV docs không ảnh hưởng Sector 11)", fontsize=12, fontweight="bold")
    ax3.set_ylabel("Số lượng văn bản", fontsize=10)
    ax3.set_ylim(0, max(vals3) * 1.35)
    ax3.grid(True, alpha=0.3, axis="y")

    # ----------------------------------------------------
    # Panel 4: Macro Policy to Sector Linkage
    # ----------------------------------------------------
    ax4 = fig.add_subplot(2, 2, 4)
    sec_counts = report["macro_policy_classification"]["sector_linkage_counts"]
    
    sec_labels_map = {
        "5": "Chứng khoán (5)",
        "11": "Ngân hàng (11)",
        "3": "Bất động sản (3)",
        "21": "Vật liệu XD / Thép (21)",
        "24": "Xây dựng / Hạ tầng (24)",
        "10": "Dầu khí (10)",
        "18": "Hóa chất / Phân bón (18)",
    }
    
    sec_names = [sec_labels_map[k] for k in ["5", "11", "3", "21", "24", "10", "18"]]
    sec_vals = [sec_counts[k] for k in ["5", "11", "3", "21", "24", "10", "18"]]
    colors4 = ["#9467bd", "#2ca02c", "#ff7f0e", "#7f7f7f", "#bcbd22", "#17becf", "#8c564b"]
    
    bars4 = ax4.barh(sec_names, sec_vals, color=colors4, alpha=0.85, edgecolor="black")
    for b, val in zip(bars4, sec_vals):
        ax4.text(b.get_width() + 3, b.get_y() + b.get_height()/2, f"{val}", 
                 va="center", fontsize=9, fontweight="bold")
                 
    ax4.set_title("Panel 4: Macro-to-Sector Transmission Linkage\nSố lượng Văn bản Vĩ mô Tác động Trực tiếp tới Từng Ngành", fontsize=12, fontweight="bold")
    ax4.set_xlabel("Số lượt tác động chính sách", fontsize=10)
    ax4.set_xlim(0, max(sec_vals) * 1.2)
    ax4.grid(True, alpha=0.3, axis="x")
    ax4.invert_yaxis()

    fig.suptitle("VESTA DATA PREPROCESSING — STEP 5: TEXT PREPROCESSING & DISAMBIGUATION\nSanitizing 278k Macro Policy & 1.1M News: Boilerplate Cleaning, MinHash LSH & Sector Disambiguation",
                 fontsize=15, fontweight="bold", y=0.98)
                 
    os.makedirs(os.path.dirname(OUT_PNG_PIPELINE), exist_ok=True)
    plt.savefig(OUT_PNG_PIPELINE, bbox_inches="tight")
    plt.savefig(OUT_PNG_ARTIFACT, bbox_inches="tight")
    plt.close()
    print(f"[OK] Visual diagnostics saved to:\n - {OUT_PNG_PIPELINE}\n - {OUT_PNG_ARTIFACT}")


if __name__ == "__main__":
    generate_visualizations()
