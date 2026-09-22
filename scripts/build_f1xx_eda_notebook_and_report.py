"""Script to generate the interactive Jupyter Notebook and Master Visualization Dashboard
for the F1xx Preprocessing & Data Enrichment Session.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import duckdb

# Ensure UTF-8 output
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def generate_comprehensive_dashboard(out_dir: pathlib.Path) -> str:
    """Generates a publication-grade 3x3 dashboard synthesizing all 11 preprocessing techniques."""
    plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
    fig = plt.figure(figsize=(24, 18), dpi=150)
    fig.patch.set_facecolor("#f8f9fa")
    gs = gridspec.GridSpec(3, 3, figure=fig, hspace=0.35, wspace=0.28)

    # -------------------------------------------------------------
    # 1. Panel (0, 0): Temporal Alignment & Timestamp Distribution
    # -------------------------------------------------------------
    ax1 = fig.add_subplot(gs[0, 0])
    with open(out_dir / "temporal_alignment_audit_report.json", "r", encoding="utf-8") as f:
        temp_data = json.load(f)["audit_1_1_event_session"]
    
    categories = ["After-Close\n(>=15:00)", "Trading Hours\n(09:00-15:00)", "Midnight\n(00:00:00)", "Weekend\n(Sat/Sun)"]
    pcts = [temp_data["after_close_pct"], temp_data["trading_hours_pct"], temp_data["midnight_pct"], temp_data["weekend_pct"]]
    colors = ["#2b5c8f", "#2ca02c", "#d62728", "#ff7f0e"]
    bars1 = ax1.bar(categories, pcts, color=colors, edgecolor="black", linewidth=1.2, alpha=0.85)
    for bar in bars1:
        y = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2.0, y + 0.8, f"{y:.1f}%", ha="center", va="bottom", fontweight="bold", fontsize=10)
    ax1.set_title("1. Temporal Alignment: News Event Session Breakdown\n(N=658,182 PIT Events)", fontsize=12, fontweight="bold", pad=10)
    ax1.set_ylabel("% of Total Events", fontsize=11, fontweight="bold")
    ax1.set_ylim(0, 50)
    ax1.grid(axis="y", linestyle="--", alpha=0.7)

    # -------------------------------------------------------------
    # 2. Panel (0, 1): Tail-Risk Sanitization: Kurtosis & Cohen's d
    # -------------------------------------------------------------
    ax2 = fig.add_subplot(gs[0, 1])
    with open(out_dir / "tail_risk_sanitization_report.json", "r", encoding="utf-8") as f:
        tail_data = json.load(f)["treatments"]
    
    t_names = [t["Treatment"].split(". ")[1] for t in tail_data]
    cohen_vals = [float(t["Cohen's d"]) for t in tail_data]
    kurt_vals = [float(t["Kurtosis"]) for t in tail_data]
    
    x_indices = np.arange(len(t_names))
    width = 0.5
    bars2 = ax2.bar(x_indices, cohen_vals, width=width, color="#1f77b4", edgecolor="black", linewidth=1.1, alpha=0.85)
    for i, bar in enumerate(bars2):
        y = bar.get_height()
        ax2.text(bar.get_x() + bar.get_width()/2.0, y + 0.003, f"d={y:.4f}\n(K={kurt_vals[i]:.1f})", ha="center", va="bottom", fontsize=8.5, fontweight="bold")
    ax2.set_xticks(x_indices)
    ax2.set_xticklabels(t_names, rotation=25, ha="right", fontsize=9)
    ax2.set_title("2. Tail-Risk Sanitization & Outlier Impact\n(Cohen's d Alpha vs Excess Kurtosis)", fontsize=12, fontweight="bold", pad=10)
    ax2.set_ylabel("Standardized Effect Size (Cohen's d)", fontsize=11, fontweight="bold")
    ax2.set_ylim(0, 0.13)
    ax2.grid(axis="y", linestyle="--", alpha=0.7)

    # -------------------------------------------------------------
    # 3. Panel (0, 2): RankGauss Transformation vs Raw Power-Law
    # -------------------------------------------------------------
    ax3 = fig.add_subplot(gs[0, 2])
    with open(out_dir / "rankgauss_report.json", "r", encoding="utf-8") as f:
        rg_data = json.load(f)["results"]["hpg_trading_volume"]
    
    raw_m = rg_data["raw_metrics"]
    rg_m = rg_data["rankgauss_metrics"]
    
    metrics_names = ["Skewness", "Excess Kurtosis (log10)", "Normality P-Val"]
    raw_scores = [raw_m["skewness"], np.log10(max(1.0, raw_m["excess_kurtosis"])), raw_m["normality_p_value"]]
    rg_scores = [rg_m["skewness"], np.log10(max(1.0, abs(rg_m["excess_kurtosis"]) + 1.0)), rg_m["normality_p_value"]]
    
    x = np.arange(len(metrics_names))
    b_width = 0.35
    ax3.bar(x - b_width/2, raw_scores, b_width, label="Raw Volume (Skewed)", color="#e74c3c", edgecolor="black", alpha=0.85)
    ax3.bar(x + b_width/2, rg_scores, b_width, label="RankGauss N(0, 1)", color="#27ae60", edgecolor="black", alpha=0.85)
    ax3.set_xticks(x)
    ax3.set_xticklabels(metrics_names, fontsize=10, fontweight="bold")
    ax3.set_title("3. RankGauss Normalization: HPG Trading Volume\n(Skew 3.25->0.0, Normality p: 0.0->0.91)", fontsize=12, fontweight="bold", pad=10)
    ax3.legend(frameon=True, facecolor="white", loc="upper right")
    ax3.grid(axis="y", linestyle="--", alpha=0.7)

    # -------------------------------------------------------------
    # 4. Panel (1, 0): Scaler Stress Test under 100x Outlier Shock
    # -------------------------------------------------------------
    ax4 = fig.add_subplot(gs[1, 0])
    with open(out_dir / "rankgauss_report.json", "r", encoding="utf-8") as f:
        stress_data = json.load(f)["results"]["scaler_stress_test"]
    
    scalers = ["MinMax Scaler", "Standard Z-Score", "Log1p Transform", "RankGauss"]
    disruptions = [
        stress_data["relative_disruption_minmax"] * 100,
        stress_data["mean_absolute_disruption_zscore"] * 100,
        stress_data["mean_absolute_disruption_log1p"] * 100,
        stress_data["mean_absolute_disruption_rankgauss"] * 100
    ]
    bar_colors = ["#c0392b", "#d35400", "#f39c12", "#2ecc71"]
    bars4 = ax4.bar(scalers, disruptions, color=bar_colors, edgecolor="black", linewidth=1.1, alpha=0.85)
    for bar in bars4:
        y = bar.get_height()
        ax4.text(bar.get_x() + bar.get_width()/2.0, y + 1.5, f"{y:.2f}%", ha="center", va="bottom", fontweight="bold", fontsize=10)
    ax4.set_title("4. Scaler Disruption Under 100x Extreme Shock\n(RankGauss Resilience = 0.22% disruption)", fontsize=12, fontweight="bold", pad=10)
    ax4.set_ylabel("Mean Feature Space Disruption (%)", fontsize=11, fontweight="bold")
    ax4.set_ylim(0, 115)
    ax4.grid(axis="y", linestyle="--", alpha=0.7)

    # -------------------------------------------------------------
    # 5. Panel (1, 1): FFD Grid Search: Stationarity vs Memory
    # -------------------------------------------------------------
    ax5 = fig.add_subplot(gs[1, 1])
    with open(out_dir / "fractional_differentiation_report.json", "r", encoding="utf-8") as f:
        ffd_grid = json.load(f)["vnindex"]["grid"]
    
    d_vals = [pt["d"] for pt in ffd_grid]
    adf_stats = [pt["adf_stat"] for pt in ffd_grid]
    corrs = [pt["corr_pearson"] for pt in ffd_grid]
    crit_5 = ffd_grid[0]["crit_5pct"]
    
    color_adf = "#d62728"
    color_corr = "#1f77b4"
    
    ax5.plot(d_vals, adf_stats, color=color_adf, marker="o", linewidth=2.2, label="ADF Test Statistic (t)")
    ax5.axhline(crit_5, color="darkred", linestyle="--", alpha=0.8, label="5% Critical Value (-2.86)")
    ax5.set_xlabel("Differentiation Order (d)", fontsize=11, fontweight="bold")
    ax5.set_ylabel("ADF Statistic (Stationarity)", color=color_adf, fontsize=11, fontweight="bold")
    ax5.tick_params(axis='y', labelcolor=color_adf)
    ax5.axvline(0.20, color="purple", linestyle=":", linewidth=2, label="Optimal d* = 0.20")
    
    ax5_twin = ax5.twinx()
    ax5_twin.plot(d_vals, corrs, color=color_corr, marker="s", linewidth=2.2, label="Pearson Memory Corr (r)")
    ax5_twin.set_ylabel("Correlation to Original Price (Memory)", color=color_corr, fontsize=11, fontweight="bold")
    ax5_twin.tick_params(axis='y', labelcolor=color_corr)
    ax5_twin.set_ylim(0.0, 1.05)
    
    lines_1, labels_1 = ax5.get_legend_handles_labels()
    lines_2, labels_2 = ax5_twin.get_legend_handles_labels()
    ax5.legend(lines_1 + lines_2, labels_1 + labels_2, loc="lower left", frameon=True, facecolor="white", fontsize=8.5)
    ax5.set_title("5. Fixed-Width FFD: Stationarity vs Memory Preservation\n(Optimal d*=0.20 Achieves ADF p<0.01 & Corr>0.90)", fontsize=12, fontweight="bold", pad=10)

    # -------------------------------------------------------------
    # 6. Panel (1, 2): NMAR Reporting Status Risk Multipliers
    # -------------------------------------------------------------
    ax6 = fig.add_subplot(gs[1, 2])
    with open(out_dir / "nmar_missing_report.json", "r", encoding="utf-8") as f:
        nmar_stocks = json.load(f)["stock_reporting_status"]
    
    statuses = [s["reporting_status"] for s in nmar_stocks]
    vol_mults = [s["volatility_multiplier"] for s in nmar_stocks]
    tail_losses = [abs(s["p05_tail_loss"]) for s in nmar_stocks]
    
    x = np.arange(len(statuses))
    w = 0.35
    ax6.bar(x - w/2, vol_mults, w, label="Volatility Multiplier", color="#3498db", edgecolor="black", alpha=0.85)
    ax6_twin = ax6.twinx()
    ax6_twin.plot(x + w/2, tail_losses, color="#e74c3c", marker="D", linewidth=2.5, label="5% Tail Loss Risk (%)")
    ax6_twin.set_ylabel("P05 Tail Loss (%)", color="#e74c3c", fontsize=11, fontweight="bold")
    ax6_twin.tick_params(axis='y', labelcolor="#e74c3c")
    
    ax6.set_xticks(x)
    ax6.set_xticklabels([s.replace(" ", "\n") for s in statuses], fontsize=9)
    ax6.set_ylabel("Historical Volatility Multiplier", color="#3498db", fontsize=11, fontweight="bold")
    ax6.set_title("6. NMAR Missing Data: Reporting Delinquency vs Risk\n(Delinquent & Seasoned Stocks Face 1.37x-1.76x Volatility)", fontsize=12, fontweight="bold", pad=10)
    ax6.grid(axis="y", linestyle="--", alpha=0.7)

    # -------------------------------------------------------------
    # 7. Panel (2, 0): Gray Code vs Binary Hamming Transitions
    # -------------------------------------------------------------
    ax7 = fig.add_subplot(gs[2, 0])
    with open(out_dir / "gray_code_report.json", "r", encoding="utf-8") as f:
        gray_data = json.load(f)
    
    gray_jumps = gray_data["gray_hamming_transitions"]
    bin_jumps = gray_data["standard_binary_hamming_transitions"]
    transitions = np.arange(1, len(gray_jumps) + 1)
    
    ax7.step(transitions, bin_jumps, where="mid", color="#e74c3c", linewidth=2.2, label="Standard Binary (Spikes up to 4 bits)")
    ax7.step(transitions, gray_jumps, where="mid", color="#27ae60", linewidth=2.8, label="Cyclic Gray Code (Strictly 1 bit everywhere)")
    ax7.set_xlabel("Macro Regime Transition Sequence (15 steps)", fontsize=11, fontweight="bold")
    ax7.set_ylabel("Hamming Bit Distance (Bits Changed)", fontsize=11, fontweight="bold")
    ax7.set_ylim(0, 5)
    ax7.set_title("7. Gray Code Encoding: Zero-Disruption Transitions\n(Prevents 4-bit Neural Glitches at Regime Shift)", fontsize=12, fontweight="bold", pad=10)
    ax7.legend(frameon=True, facecolor="white", loc="upper left")
    ax7.grid(True, linestyle="--", alpha=0.7)

    # -------------------------------------------------------------
    # 8. Panel (2, 1): Clustered Block Bootstrap vs IID Bootstrap
    # -------------------------------------------------------------
    ax8 = fig.add_subplot(gs[2, 1])
    with open(out_dir / "regime_bootstrap_report.json", "r", encoding="utf-8") as f:
        boot_data = json.load(f)["bootstrap_audit"]
    
    iid_ci = boot_data["iid_bootstrap"]["mean_ci_95"]
    block_ci = boot_data["clustered_block_bootstrap"]["mean_ci_95"]
    exp_factor = boot_data["ci_expansion_factor"]
    
    models = ["Naive I.I.D. Bootstrap", "Clustered Block Bootstrap\n(866 Weekly Clusters)"]
    lowers = [iid_ci[0], block_ci[0]]
    uppers = [iid_ci[1], block_ci[1]]
    means = [(lowers[0] + uppers[0])/2, (lowers[1] + uppers[1])/2]
    errors = [[means[0] - lowers[0], means[1] - lowers[1]], [uppers[0] - means[0], uppers[1] - means[1]]]
    
    ax8.errorbar(models, means, yerr=errors, fmt="o", color="#2c3e50", ecolor="#8e44ad", elinewidth=3, capsize=10, capthick=2.5, markersize=8)
    ax8.set_ylabel("Mean Return 95% Confidence Interval (%)", fontsize=11, fontweight="bold")
    ax8.set_ylim(0, 2.5)
    ax8.text(0.5, 2.1, f"CI Expansion Factor = {exp_factor:.2f}x\n(Accounts for Cross-Asset Clustering)", ha="center", fontsize=11, fontweight="bold", bbox=dict(boxstyle="round,pad=0.5", facecolor="#f39c12", alpha=0.3))
    ax8.set_title("8. Statistical Rigor: Block Bootstrap vs IID\n(Naive IID Severely Underestimates Variance)", fontsize=12, fontweight="bold", pad=10)
    ax8.grid(axis="y", linestyle="--", alpha=0.7)

    # -------------------------------------------------------------
    # 9. Panel (2, 2): Forward Horizon Label Return Distributions
    # -------------------------------------------------------------
    ax9 = fig.add_subplot(gs[2, 2])
    sample_csv = out_dir / "sample_preprocessed_dataset.csv"
    if sample_csv.exists():
        df_sample = pd.read_csv(sample_csv)
        ret_t5 = df_sample["ret_t5_pct"].dropna()
        ret_t30 = df_sample["ret_t30_pct"].dropna()
        
        ax9.hist(ret_t5, bins=25, alpha=0.6, color="#2980b9", label="T+5 Realized Return (%)", edgecolor="black")
        ax9.hist(ret_t30, bins=25, alpha=0.5, color="#8e44ad", label="T+30 Realized Return (%)", edgecolor="black")
        ax9.axvline(0, color="black", linestyle="--", linewidth=1.2)
        ax9.set_xlabel("Winsorized Forward Return (%)", fontsize=11, fontweight="bold")
        ax9.set_ylabel("Sample Event Frequency", fontsize=11, fontweight="bold")
        ax9.set_title("9. F104 Forward Target Horizons\n(Multi-Horizon Realized Return Distributions)", fontsize=12, fontweight="bold", pad=10)
        ax9.legend(frameon=True, facecolor="white", loc="upper right")
        ax9.grid(True, linestyle="--", alpha=0.7)
    
    # Global Title
    fig.suptitle("VESTA F1XX QUANTITATIVE PREPROCESSING & ENRICHMENT PIPELINE\nCOMPREHENSIVE EXPLORATORY DATA ANALYSIS (EDA) MASTER DASHBOARD", fontsize=18, fontweight="bold", y=0.995)
    
    out_img = out_dir / "f1xx_comprehensive_reprocessing_dashboard.png"
    plt.savefig(out_img, bbox_inches="tight")
    plt.close()
    print(f"[+] Master Dashboard successfully generated at: {out_img}")
    return str(out_img)


def generate_jupyter_notebook(out_notebook_paths: list[pathlib.Path], out_dir: pathlib.Path) -> None:
    """Generates a comprehensive Jupyter Notebook (.ipynb) for interactive EDA."""
    nb_cells = [
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "# 🔬 VESTA F1XX REPROCESSING SESSION: MASTER EXPLORATORY DATA ANALYSIS (EDA)\n",
                "## Kiểm Toán Định Lượng & Trực Quan Hóa Chi Tiết 11 Kỹ Thuật Tiền Xử Lý Dữ Liệu\n",
                "---\n",
                "**Dự án:** VESTA (*Vietnamese Equity Sentiment-Triggered Agent*)  \n",
                "**Phân tầng:** Tier F1xx — Data Integrity, Point-in-Time Join & Enterprise Feature Engineering  \n",
                "**Mục tiêu Notebook:** Cung cấp toàn bộ công cụ kiểm toán trực quan (Visual & Statistical Audit), tải dữ liệu mẫu, biểu diễn các phân phối trước và sau chuẩn hóa, kiểm định tính dừng toán học và độ tin cậy của nhãn mục tiêu."
            ]
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "# 1. Khởi tạo môi trường, thiết lập đồ họa và tải các thư viện định lượng\n",
                "import os\n",
                "import sys\n",
                "import json\n",
                "import pathlib\n",
                "import numpy as np\n",
                "import pandas as pd\n",
                "import matplotlib.pyplot as plt\n",
                "import seaborn as sns\n",
                "import duckdb\n",
                "\n",
                "# Thiết lập giao diện đồ họa chuẩn học thuật\n",
                "plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')\n",
                "plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial']\n",
                "plt.rcParams['figure.dpi'] = 120\n",
                "\n",
                "out_dir = pathlib.Path('../test_pipeline/out').resolve()\n",
                "if not out_dir.exists():\n",
                "    out_dir = pathlib.Path('test_pipeline/out').resolve()\n",
                "\n",
                "print(f\"Thư mục dữ liệu kết quả: {out_dir}\")\n",
                "print(f\"Số tệp kết quả tìm thấy: {len(list(out_dir.glob('*')))}\")"
            ]
        },
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "### 📊 Tổng Quan Toàn Bộ Kết Quả Nghiệm Thu Tier F1xx\n",
                "Đọc báo cáo tổng hợp `test_pipeline_run_report.json` và bảng điều khiển KPI của F101, F102, F103, F104."
            ]
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "with open(out_dir / 'test_pipeline_run_report.json', 'r', encoding='utf-8') as f:\n",
                "    pipeline_report = json.load(f)\n",
                "\n",
                "stages = pipeline_report['stages']\n",
                "summary_data = []\n",
                "for k in ['F101', 'F102', 'F103', 'F104']:\n",
                "    if k in stages:\n",
                "        summary_data.append({\n",
                "            'Tier Feature': k,\n",
                "            'Status': stages[k].get('status', 'N/A'),\n",
                "            'Metric Summary': str(stages[k].get('coverage', stages[k].get('summary', stages[k].get('valid_symbols_count', 'OK'))))\n",
                "        })\n",
                "\n",
                "df_stages = pd.DataFrame(summary_data)\n",
                "display(df_stages)"
            ]
        },
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "### 🕒 Kỹ Thuật 1: Temporal Alignment & Point-in-Time Session Breakdown\n",
                "Kiểm toán 658,182 sự kiện trong `core.pit_events`: Phân loại mốc thời gian xuất bản (Sau giờ giao dịch 40.4%, Nửa đêm 25.7%, Trong giờ giao dịch 27.0%, Cuối tuần 1.1%)."
            ]
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "with open(out_dir / 'temporal_alignment_audit_report.json', 'r', encoding='utf-8') as f:\n",
                "    temp_audit = json.load(f)['audit_1_1_event_session']\n",
                "\n",
                "fig, ax = plt.subplots(figsize=(10, 5))\n",
                "labels = ['Sau giờ đóng cửa (>=15:00)', 'Trong phiên (09:00-15:00)', 'Mốc 00:00:00 (Midnight)', 'Cuối tuần']\n",
                "values = [temp_audit['after_close_pct'], temp_audit['trading_hours_pct'], temp_audit['midnight_pct'], temp_audit['weekend_pct']]\n",
                "colors = ['#2b5c8f', '#2ca02c', '#d62728', '#ff7f0e']\n",
                "\n",
                "bars = ax.bar(labels, values, color=colors, edgecolor='black', alpha=0.85)\n",
                "for bar in bars:\n",
                "    y = bar.get_height()\n",
                "    ax.text(bar.get_x() + bar.get_width()/2, y + 0.8, f'{y:.2f}%', ha='center', va='bottom', fontweight='bold')\n",
                "\n",
                "ax.set_title('Phân Bố Mốc Thời Gian Xuất Bản Tin Tức (Temporal Alignment Audit)', fontsize=13, fontweight='bold')\n",
                "ax.set_ylabel('% Tỷ Lệ Trong Tổng Số 658,182 Sự Kiện')\n",
                "ax.set_ylim(0, 50)\n",
                "plt.xticks(rotation=15)\n",
                "plt.tight_layout()\n",
                "plt.show()"
            ]
        },
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "### 🛡️ Kỹ Thuật 2 & 3: Extreme Tail-Risk Sanitization & Asymmetric Winsorization\n",
                "Bóc tách vụ thao túng giá cổ phiếu XDC tăng $+3,021\%$ với thanh khoản 100 cổ phiếu/phiên. Xem xét sự suy giảm của hệ số Kurtosis từ 4,355 xuống 7.82 và sự gia tăng của hệ số Cohen's d từ 0.0576 lên 0.0984."
            ]
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "with open(out_dir / 'tail_risk_sanitization_report.json', 'r', encoding='utf-8') as f:\n",
                "    tail_data = json.load(f)\n",
                "\n",
                "df_treatments = pd.DataFrame(tail_data['treatments'])\n",
                "print(\"Top 5 cổ phiếu ngoại lai cực đoan nhất:\")\n",
                "display(pd.DataFrame(tail_data['top10_outliers']).head(5))\n",
                "\n",
                "fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 5))\n",
                "df_treatments['Cohen_d_num'] = df_treatments[\"Cohen's d\"].astype(float)\n",
                "df_treatments['Kurtosis_num'] = df_treatments['Kurtosis'].astype(float)\n",
                "\n",
                "# Biểu đồ Cohen's d\n",
                "ax1.barh(df_treatments['Treatment'], df_treatments['Cohen_d_num'], color='#1f77b4', edgecolor='black', alpha=0.85)\n",
                "ax1.set_title(\"Hệ Số Tác Động Chuẩn Hóa (Cohen's d)\", fontsize=12, fontweight='bold')\n",
                "ax1.set_xlabel(\"Cohen's d (Càng lớn tín hiệu Alpha càng mạnh)\")\n",
                "\n",
                "# Biểu đồ Kurtosis\n",
                "ax2.barh(df_treatments['Treatment'], np.log10(df_treatments['Kurtosis_num']), color='#e74c3c', edgecolor='black', alpha=0.85)\n",
                "ax2.set_title(\"Hệ Số Nhọn Phân Phối (Log10 Kurtosis - Đuôi Dày)\", fontsize=12, fontweight='bold')\n",
                "ax2.set_xlabel(\"Log10(Excess Kurtosis)\")\n",
                "\n",
                "plt.tight_layout()\n",
                "plt.show()"
            ]
        },
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "### 📈 Kỹ Thuật 4: RankGauss Normalization & Thử Nghiệm Chịu Tải Sốc 100x (Stress Test)\n",
                "So sánh khả năng kháng sốc của RankGauss so với MinMax, Z-Score và Log1p khi bị chèn một ngoại lai cực đại gấp 100 lần."
            ]
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "with open(out_dir / 'rankgauss_report.json', 'r', encoding='utf-8') as f:\n",
                "    rg_data = json.load(f)['results']\n",
                "\n",
                "stress = rg_data['scaler_stress_test']\n",
                "scalers = ['MinMax Scaler', 'Standard Z-Score', 'Log1p Transform', 'RankGauss']\n",
                "disruptions = [\n",
                "    stress['relative_disruption_minmax'] * 100,\n",
                "    stress['mean_absolute_disruption_zscore'] * 100,\n",
                "    stress['mean_absolute_disruption_log1p'] * 100,\n",
                "    stress['mean_absolute_disruption_rankgauss'] * 100\n",
                "]\n",
                "\n",
                "fig, ax = plt.subplots(figsize=(9, 5))\n",
                "bars = ax.bar(scalers, disruptions, color=['#c0392b', '#d35400', '#f39c12', '#2ecc71'], edgecolor='black', alpha=0.85)\n",
                "for bar in bars:\n",
                "    y = bar.get_height()\n",
                "    ax.text(bar.get_x() + bar.get_width()/2, y + 1.5, f\"{y:.2f}%\", ha='center', fontweight='bold')\n",
                "\n",
                "ax.set_title(\"Mức Độ Xáo Trộn Không Gian Đặc Trưng Khi Gặp Sốc Ngoại Lai 100x\", fontsize=13, fontweight='bold')\n",
                "ax.set_ylabel(\"% Xáo Trộn Giá Trị Toàn Bộ Mẫu\")\n",
                "ax.set_ylim(0, 115)\n",
                "plt.tight_layout()\n",
                "plt.show()"
            ]
        },
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "### 🔄 Kỹ Thuật 6: Fixed-Width Window Fractional Differentiation (FFD)\n",
                "Tìm kiếm điểm cân bằng tối ưu giữa Tính dừng toán học (Stationary - Kiểm định ADF $p < 0.01$) và Bảo toàn ký ức chuỗi giá (Pearson Correlation $> 0.90$)."
            ]
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "with open(out_dir / 'fractional_differentiation_report.json', 'r', encoding='utf-8') as f:\n",
                "    ffd_grid = json.load(f)['vnindex']['grid']\n",
                "\n",
                "df_ffd = pd.DataFrame(ffd_grid)\n",
                "\n",
                "fig, ax1 = plt.subplots(figsize=(10, 5))\n",
                "color = '#d62728'\n",
                "ax1.plot(df_ffd['d'], df_ffd['adf_stat'], marker='o', color=color, label='Thống Kê ADF (t-stat)')\n",
                "ax1.axhline(-2.862, color='darkred', linestyle='--', label='Ngưỡng Dừng 5% (-2.862)')\n",
                "ax1.set_xlabel('Bậc Vi Phân Phân Số (d)')\n",
                "ax1.set_ylabel('Thống Kê ADF', color=color)\n",
                "ax1.tick_params(axis='y', labelcolor=color)\n",
                "ax1.axvline(0.20, color='purple', linestyle=':', linewidth=2, label='d* = 0.20 (Tối ưu)')\n",
                "\n",
                "ax2 = ax1.twinx()\n",
                "color2 = '#1f77b4'\n",
                "ax2.plot(df_ffd['d'], df_ffd['corr_pearson'], marker='s', color=color2, label='Hệ Số Tương Quan Ký Ức (Pearson)')\n",
                "ax2.set_ylabel('Tương Quan Với Giá Gốc', color=color2)\n",
                "ax2.tick_params(axis='y', labelcolor=color2)\n",
                "\n",
                "lines1, labels1 = ax1.get_legend_handles_labels()\n",
                "lines2, labels2 = ax2.get_legend_handles_labels()\n",
                "ax1.legend(lines1 + lines2, labels1 + labels2, loc='lower left')\n",
                "plt.title('Đường Cong Cân Bằng Giữa Tính Dừng ADF Và Bảo Tồn Ký Ức Chuỗi Giá (FFD)', fontsize=13, fontweight='bold')\n",
                "plt.tight_layout()\n",
                "plt.show()"
            ]
        },
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "### 📑 Kỹ Thuật 5: NMAR (Not-Missing-At-Random) & Hệ Số Rủi Ro Chậm Nộp BCTC\n",
                "Phân tích mối tương quan giữa sự chậm trễ nộp BCTC và rủi ro sụt giảm lợi nhuận (Tail Risk)."
            ]
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "with open(out_dir / 'nmar_missing_report.json', 'r', encoding='utf-8') as f:\n",
                "    nmar_data = json.load(f)['stock_reporting_status']\n",
                "\n",
                "df_nmar = pd.DataFrame(nmar_data)\n",
                "display(df_nmar[['reporting_status', 'count', 'pct_of_events', 'volatility_multiplier', 'p05_tail_loss']])"
            ]
        },
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "### 🔀 Kỹ Thuật 9: Gray Code Macro Regime Transition\n",
                "Khảo sát bước nhảy khoảng cách Hamming giữa Gray Code (luôn $= 1$ bit) so với Binary thông thường (nhảy đột biến tới 4 bits)."
            ]
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "with open(out_dir / 'gray_code_report.json', 'r', encoding='utf-8') as f:\n",
                "    gray_report = json.load(f)\n",
                "\n",
                "g_jumps = gray_report['gray_hamming_transitions']\n",
                "b_jumps = gray_report['standard_binary_hamming_transitions']\n",
                "\n",
                "plt.figure(figsize=(10, 4))\n",
                "plt.step(range(1, len(b_jumps) + 1), b_jumps, where='mid', label='Binary Thông Thường (Gây sốc mạng nơ-ron)', color='#e74c3c', linewidth=2)\n",
                "plt.step(range(1, len(g_jumps) + 1), g_jumps, where='mid', label='Gray Code Tuần Hoàn (Độ mượt tuyệt đối = 1)', color='#27ae60', linewidth=2.5)\n",
                "plt.title('Khoảng Cách Hamming Khi Chuyển Dịch Giữa 16 Chế Độ Thị Trường', fontsize=13, fontweight='bold')\n",
                "plt.xlabel('Bước Chuyển Pha Thị Trường')\n",
                "plt.ylabel('Số Bit Bị Thay Đổi (Bits Changed)')\n",
                "plt.ylim(0, 5)\n",
                "plt.legend()\n",
                "plt.tight_layout()\n",
                "plt.show()"
            ]
        },
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "### 📦 Khảo Sát Tập Mẫu Dữ Liệu Parquet Đã Tiền Xử Lý (F104 Features & Targets)\n",
                "Tải trực tiếp bảng `sample_preprocessed_dataset.csv` và ma trận đặc trưng `features_sample_train.parquet`."
            ]
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "sample_csv = out_dir / 'sample_preprocessed_dataset.csv'\n",
                "if sample_csv.exists():\n",
                "    df_sample = pd.read_csv(sample_csv)\n",
                "    print(f\"Kích thước tập mẫu: {df_sample.shape}\")\n",
                "    display(df_sample.head(5))\n",
                "\n",
                "    # Ma trận tương quan giữa các biến định lượng\n",
                "    quant_cols = ['sentiment_score', 'rankgauss_sentiment_z', 'ret_t5_pct', 'ret_t30_pct', 'winsorized_diff_pct', 'rankgauss_volume_z']\n",
                "    available_cols = [c for c in quant_cols if c in df_sample.columns]\n",
                "    \n",
                "    plt.figure(figsize=(8, 6))\n",
                "    sns.heatmap(df_sample[available_cols].corr(), annot=True, cmap='coolwarm', fmt='.2f', linewidths=0.5)\n",
                "    plt.title('Ma Trận Tương Quan Đặc Trưng Tiền Xử Lý F104', fontsize=13, fontweight='bold')\n",
                "    plt.tight_layout()\n",
                "    plt.show()"
            ]
        },
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "## 🏁 Kết Luận & Đánh Giá Tổng Thể\n",
                "1. **Bảo toàn 100% Zero Look-Ahead Bias:** Phép nối Point-in-Time F102 và kiểm toán F101 đã ngăn chặn toàn bộ hiện tượng rò rỉ thông tin tương lai.\n",
                "2. **Triệt tiêu nhiễu thao túng đuôi dày:** Bóc tách các mã như XDC và áp dụng Asymmetric Winsorization khống chế Kurtosis từ 4,355 về mức 7.82, nâng hệ số Cohen's d lên $0.0984$.\n",
                "3. **Chuẩn hóa RankGauss vững chắc:** Đảm bảo các đặc trưng tài chính luôn tuân theo phân phối chuẩn $\\mathcal{N}(0, 1)$, miễn nhiễm trước các cú sốc ngoại lai 100x.\n",
                "4. **Tập dữ liệu F104 sẵn sàng:** 384,431 mẫu đa phương thức đã hoàn thiện, đảm bảo điều kiện tiên quyết vững chắc để bước vào phân tầng F2xx và F3xx."
            ]
        }
    ]

    nb_dict = {
        "cells": nb_cells,
        "metadata": {
            "language_info": {
                "name": "python",
                "version": "3.12"
            },
            "kernelspec": {
                "display_name": "Python 3 (.venv)",
                "language": "python",
                "name": "python3"
            }
        },
        "nbformat": 4,
        "nbformat_minor": 4
    }

    for p in out_notebook_paths:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(nb_dict, f, ensure_ascii=False, indent=1)
        print(f"[+] Jupyter Notebook generated at: {p}")


def main():
    root = pathlib.Path(__file__).resolve().parents[1]
    out_dir = root / "test_pipeline" / "out"
    print(f"[*] Reading sample results from: {out_dir}")

    # 1. Generate master dashboard image
    dash_path = generate_comprehensive_dashboard(out_dir)

    # 2. Generate Jupyter notebooks in both locations
    nb_paths = [
        root / "notebooks" / "F1XX_REPROCESSING_EDA.ipynb",
        root / "test_pipeline" / "notebooks" / "F1XX_REPROCESSING_EDA.ipynb"
    ]
    generate_jupyter_notebook(nb_paths, out_dir)

    print("\n[SUCCESS] All EDA visualizations, dashboard, and notebooks successfully created!")


if __name__ == "__main__":
    main()
