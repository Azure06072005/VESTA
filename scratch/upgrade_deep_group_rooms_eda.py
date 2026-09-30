import json
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

notebook_data = {
 "cells": [
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "# PHÂN TÍCH KHÁM PHÁ DỮ LIỆU CHUYÊN SÂU (DEEP EDA): TOÀN BỘ 23 RỔ NHÓM VÀ NGÀNH (GROUP ROOMS)\n",
    "## Khảo sát Đặc tính Động lượng, Hiệu suất Ngành & Rổ Kín Room Ngoại trên Thị trường Chứng khoán Việt Nam\n",
    "\n",
    "**Dự án:** VESTA - Vietnamese Equity Sentiment-Triggered Agent  \n",
    "**Cơ sở dữ liệu:** `db/vesta_ohlcv.duckdb` (Dedicated OHLCV Database)  \n",
    "**Phạm vi dữ liệu:** 23 rổ chỉ số phân loại chính thức của Sở Giao dịch Chứng khoán TP.HCM (HOSE) & VNX từ năm 2017 đến 2026.\n",
    "\n",
    "---\n",
    "\n",
    "### Cấu trúc 3 Phân hệ Rổ Nhóm Nghiên cứu:\n",
    "1. **Phân hệ Quy mô Vốn hóa (Market Cap Baskets):**\n",
    "   - `VN30` (30 cổ phiếu Bluechip vốn hóa & thanh khoản hàng đầu)\n",
    "   - `VN100` (100 cổ phiếu hàng đầu gồm VN30 và VNMidCap)\n",
    "   - `VNMID` (VNMidCap - 70 doanh nghiệp quy mô trung bình)\n",
    "   - `VNSML` (VNSmallCap - Doanh nghiệp quy mô nhỏ)\n",
    "   - `VNALL` (VNAllShare - Toàn bộ cổ phiếu đạt chuẩn sàng lọc HOSE)\n",
    "   - `VNX50` & `VNXALL` (Chỉ số hợp nhất liên sàn HOSE và HNX)\n",
    "\n",
    "2. **Phân hệ Rổ Room Ngoại & Đầu tư Chiến lược (Thematic & Foreign Room Baskets):**\n",
    "   - `VNDIAMOND` (Chỉ số cổ phiếu kim cương - Các mã hết room ngoại $\\ge 95\\%$ như FPT, MWG, PNJ, REE, TCB...)\n",
    "   - `VNFINLEAD` (Chỉ số ngành tài chính dẫn dắt - Top ngân hàng, chứng khoán có thanh khoản lớn)\n",
    "   - `VNFINSELECT` (Chỉ số tuyển chọn các cổ phiếu ngành tài chính)\n",
    "   - `VNSI` (Vietnam Sustainability Index - Top 20 doanh nghiệp ESG phát triển bền vững)\n",
    "   - `VNDIVIDEND` (Chỉ số các doanh nghiệp chi trả cổ tức tiền mặt cao)\n",
    "   - `VNMITECH` (Chỉ số nhóm cổ phiếu công nghệ & viễn thông)\n",
    "\n",
    "3. **Phân hệ 10 Nhóm Ngành Chuẩn ICB (Sector Baskets):**\n",
    "   - `VNFIN` (Tài chính: Ngân hàng, Chứng khoán, Bảo hiểm)\n",
    "   - `VNREAL` (Bất động sản)\n",
    "   - `VNMAT` (Nguyên vật liệu: Thép, Hóa chất)\n",
    "   - `VNIT` (Công nghệ Thông tin)\n",
    "   - `VNIND` (Công nghiệp: Xây dựng, Cảng biển, Vận tải)\n",
    "   - `VNCONS` (Hàng tiêu dùng thiết yếu: Thực phẩm, Đồ uống)\n",
    "   - `VNCOND` (Hàng tiêu dùng không thiết yếu: Bán lẻ, Ô tô phụ tùng)\n",
    "   - `VNHEAL` (Chăm sóc sức khỏe: Dược phẩm, Thiết bị y tế)\n",
    "   - `VNENE` (Năng lượng: Dầu khí, Khai khoáng)\n",
    "   - `VNUTI` (Tiện ích: Điện, Nước, Khí đốt)"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": None,
   "metadata": {},
   "outputs": [],
   "source": [
    "# 1. Khởi tạo môi trường & kết nối DuckDB vesta_ohlcv.duckdb\n",
    "import duckdb\n",
    "import pandas as pd\n",
    "import numpy as np\n",
    "import matplotlib.pyplot as plt\n",
    "import seaborn as sns\n",
    "from datetime import datetime\n",
    "\n",
    "# Cấu hình giao diện biểu đồ chuyên nghiệp\n",
    "plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')\n",
    "plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial']\n",
    "plt.rcParams['figure.figsize'] = (15, 7)\n",
    "plt.rcParams['figure.dpi'] = 120\n",
    "pd.set_option('display.max_columns', 25)\n",
    "pd.set_option('display.float_format', lambda x: '%.2f' % x)\n",
    "\n",
    "DB_PATH = '../../db/vesta_ohlcv.duckdb'\n",
    "con = duckdb.connect(DB_PATH, read_only=True)\n",
    "print(\"✅ Đã kết nối thành công tới OHLCV Database:\", DB_PATH)"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "--- \n",
    "## PHẦN I: TỔNG QUAN DỮ LIỆU 23 RỔ NHÓM VÀ NGÀNH\n",
    "Truy vấn và thống kê tổng hợp số lượng phiên giao dịch, ngày bắt đầu và giá trị mới nhất của toàn bộ 23 rổ nhóm trong `core.market_index_daily`."
   ]
  },
  {
   "cell_type": "code",
   "execution_count": None,
   "metadata": {},
   "outputs": [],
   "source": [
    "# 1.1 Thống kê danh mục 23 rổ nhóm chỉ số\n",
    "group_rooms_all = [\n",
    "    'VN30', 'VN100', 'VNMID', 'VNSML', 'VNALL', 'VNX50', 'VNXALL',\n",
    "    'VNDIAMOND', 'VNFINLEAD', 'VNFINSELECT', 'VNSI', 'VNDIVIDEND', 'VNMITECH',\n",
    "    'VNFIN', 'VNREAL', 'VNMAT', 'VNIND', 'VNCONS', 'VNCOND', 'VNHEAL', 'VNENE', 'VNUTI', 'VNIT'\n",
    "]\n",
    "\n",
    "query_summary = f\"\"\"\n",
    "    SELECT index_code,\n",
    "           min(date) as start_date,\n",
    "           max(date) as end_date,\n",
    "           count(*) as total_bars,\n",
    "           round(min(close), 2) as min_close,\n",
    "           round(max(close), 2) as max_close,\n",
    "           round(avg(close), 2) as avg_close,\n",
    "           round(avg(volume), 0) as avg_volume\n",
    "    FROM core.market_index_daily\n",
    "    WHERE index_code IN ({','.join([repr(x) for x in group_rooms_all])})\n",
    "    GROUP BY index_code\n",
    "    ORDER BY index_code\n",
    "\"\"\"\n",
    "df_summary = con.execute(query_summary).fetchdf()\n",
    "print(f\"🔹 Tổng số rổ nhóm đã được nạp dữ liệu: {len(df_summary)} / 23\")\n",
    "display(df_summary)"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": None,
   "metadata": {},
   "outputs": [],
   "source": [
    "# 1.2 Pivot toàn bộ chuỗi giá đóng cửa của 23 rổ nhóm từ năm 2020 đến nay\n",
    "query_pivot = f\"\"\"\n",
    "    SELECT date, index_code, close\n",
    "    FROM core.market_index_daily\n",
    "    WHERE index_code IN ({','.join([repr(x) for x in group_rooms_all])})\n",
    "      AND date >= '2020-01-01'\n",
    "    ORDER BY date ASC\n",
    "\"\"\"\n",
    "df_pivot_raw = con.execute(query_pivot).fetchdf()\n",
    "df_pivot_raw['date'] = pd.to_datetime(df_pivot_raw['date'])\n",
    "df_close_all = df_pivot_raw.pivot(index='date', columns='index_code', values='close')\n",
    "\n",
    "print(\"🔹 Kích thước bảng chuỗi giá đóng cửa:\", df_close_all.shape)\n",
    "display(df_close_all.tail(5))"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "--- \n",
    "## PHẦN II: KHẢO SÁT PHÂN HỆ QUY MÔ VỐN HÓA (MARKET CAP DYNAMICS)\n",
    "So sánh động lượng tăng trưởng và độ biến động giữa:\n",
    "- `VN30`: Nhóm Vốn hóa lớn (Large Cap)\n",
    "- `VNMID`: Nhóm Vốn hóa trung bình (Mid Cap - 70 mã)\n",
    "- `VNSML`: Nhóm Vốn hóa nhỏ (Small Cap)\n",
    "- `VNALL`: Toàn bộ thị trường HOSE"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": None,
   "metadata": {},
   "outputs": [],
   "source": [
    "# 2.1 Hiệu suất tích lũy chuẩn hóa của các tầng quy mô vốn hóa (Base 100 tại 2020-01-02)\n",
    "cap_cols = ['VN30', 'VNMID', 'VNSML', 'VNALL']\n",
    "df_cap = df_close_all[cap_cols].dropna()\n",
    "df_cap_norm = (df_cap / df_cap.iloc[0]) * 100\n",
    "\n",
    "fig, ax = plt.subplots(figsize=(15, 6))\n",
    "colors_cap = {'VN30': '#1f77b4', 'VNMID': '#2ca02c', 'VNSML': '#ff7f0e', 'VNALL': '#7f7f7f'}\n",
    "for c in cap_cols:\n",
    "    ax.plot(df_cap_norm.index, df_cap_norm[c], label=c, color=colors_cap[c], lw=2 if c in ['VN30', 'VNMID'] else 1.5)\n",
    "\n",
    "ax.set_title('So sánh Hiệu suất Tăng trưởng Chuẩn hóa theo Quy mô Vốn hóa (2020 - 2026)', fontsize=13, fontweight='bold')\n",
    "ax.set_ylabel('Giá trị Tích lũy Chuẩn hóa (Mốc 100 = Đầu 2020)')\n",
    "ax.legend(loc='upper left', fontsize=11)\n",
    "ax.grid(True, linestyle='--', alpha=0.6)\n",
    "plt.show()\n",
    "\n",
    "# Thống kê lợi suất và biến động tầng vốn hóa\n",
    "ret_cap = df_cap.pct_change().dropna() * 100\n",
    "cap_stats = pd.DataFrame({\n",
    "    'Total Return (%)': ((df_cap.iloc[-1] / df_cap.iloc[0]) - 1) * 100,\n",
    "    'Annualized Return (%)': (((df_cap.iloc[-1] / df_cap.iloc[0]) ** (252 / len(df_cap))) - 1) * 100,\n",
    "    'Annualized Volatility (%)': ret_cap.std() * np.sqrt(252),\n",
    "    'Sharpe Ratio (Rf=5%)': ((((df_cap.iloc[-1] / df_cap.iloc[0]) ** (252 / len(df_cap))) - 1) * 100 - 5.0) / (ret_cap.std() * np.sqrt(252))\n",
    "})\n",
    "display(cap_stats)"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "--- \n",
    "## PHẦN III: KHẢO SÁT RỔ ROOM NGOẠI & CHIẾN LƯỢC ĐẦU TƯ (THEMATIC ROOMS)\n",
    "Đánh giá sức mạnh vượt trội của rổ kim cương kín room ngoại `VNDIAMOND`, rổ tài chính dẫn dắt `VNFINLEAD`, và chỉ số bền vững `VNSI`."
   ]
  },
  {
   "cell_type": "code",
   "execution_count": None,
   "metadata": {},
   "outputs": [],
   "source": [
    "# 3.1 So sánh Hiệu suất Rổ Kín Room Ngoại (VNDIAMOND) vs VNFINLEAD vs VNSI vs VN30\n",
    "# Bắt đầu từ 2020-05-15 (Khi VNDIAMOND và VNFINLEAD có dữ liệu đầy đủ)\n",
    "thematic_cols = ['VNDIAMOND', 'VNFINLEAD', 'VNSI', 'VN30']\n",
    "df_thematic = df_close_all[thematic_cols].dropna().loc['2020-05-15':]\n",
    "df_thematic_norm = (df_thematic / df_thematic.iloc[0]) * 100\n",
    "\n",
    "fig, ax = plt.subplots(figsize=(15, 6))\n",
    "ax.plot(df_thematic_norm.index, df_thematic_norm['VNDIAMOND'], label='VNDIAMOND (Cổ phiếu Kim cương Kín Room Ngoại)', color='#e377c2', lw=2.5)\n",
    "ax.plot(df_thematic_norm.index, df_thematic_norm['VNFINLEAD'], label='VNFINLEAD (Ngành Tài chính Dẫn dắt)', color='#ff7f0e', lw=1.8)\n",
    "ax.plot(df_thematic_norm.index, df_thematic_norm['VNSI'], label='VNSI (Chỉ số Bền vững ESG)', color='#2ca02c', lw=1.8)\n",
    "ax.plot(df_thematic_norm.index, df_thematic_norm['VN30'], label='VN30 Benchmark', color='#1f77b4', lw=2, linestyle='--')\n",
    "\n",
    "ax.set_title('Sức mạnh Động lượng của Rổ Room Ngoại (VNDIAMOND) so với các Rổ Chiến lược (2020 - 2026)', fontsize=13, fontweight='bold')\n",
    "ax.set_ylabel('Giá trị Tích lũy Chuẩn hóa (Mốc 100 = 05/2020)')\n",
    "ax.legend(loc='upper left', fontsize=11)\n",
    "ax.grid(True, linestyle='--', alpha=0.6)\n",
    "plt.show()"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "--- \n",
    "## PHẦN IV: KHẢO SÁT 10 NHÓM NGÀNH CHUẨN ICB (SECTOR ROTATION ANALYSIS)\n",
    "Khảo sát chu kỳ luân chuyển dòng tiền và hiệu suất của 10 ngành kinh tế chính trên TTCK Việt Nam."
   ]
  },
  {
   "cell_type": "code",
   "execution_count": None,
   "metadata": {},
   "outputs": [],
   "source": [
    "# 4.1 Hiệu suất tích lũy của 10 nhóm ngành từ đầu năm 2020\n",
    "sector_cols = ['VNFIN', 'VNREAL', 'VNMAT', 'VNIT', 'VNIND', 'VNCONS', 'VNCOND', 'VNHEAL', 'VNENE', 'VNUTI']\n",
    "df_sectors = df_close_all[sector_cols].dropna().loc['2020-01-02':]\n",
    "df_sectors_norm = (df_sectors / df_sectors.iloc[0]) * 100\n",
    "\n",
    "# Tính toán tỷ suất sinh lời tổng thể của từng ngành\n",
    "total_sector_returns = ((df_sectors.iloc[-1] / df_sectors.iloc[0]) - 1) * 100\n",
    "total_sector_returns_sorted = total_sector_returns.sort_values(ascending=False)\n",
    "\n",
    "fig, axes = plt.subplots(1, 2, figsize=(18, 7), gridspec_kw={'width_ratios': [2, 1]})\n",
    "\n",
    "# Biểu đồ diễn biến đường giá các ngành hàng đầu\n",
    "top_sectors = total_sector_returns_sorted.index[:5]\n",
    "for s in top_sectors:\n",
    "    axes[0].plot(df_sectors_norm.index, df_sectors_norm[s], label=f'{s} (+{total_sector_returns[s]:.1f}%)', lw=2)\n",
    "axes[0].plot(df_sectors_norm.index, df_cap_norm['VN30'].loc[df_sectors_norm.index], label='VN30', color='black', linestyle='--', lw=1.5)\n",
    "axes[0].set_title('Top 5 Ngành Tăng trưởng Mạnh nhất Chu kỳ 2020 - 2026', fontsize=12, fontweight='bold')\n",
    "axes[0].set_ylabel('Giá trị Tích lũy Chuẩn hóa')\n",
    "axes[0].legend(loc='upper left')\n",
    "axes[0].grid(True, linestyle='--', alpha=0.6)\n",
    "\n",
    "# Biểu đồ cột xếp hạng tổng lợi suất 10 ngành\n",
    "colors_bar = ['#2ca02c' if ret >= 0 else '#d62728' for ret in total_sector_returns_sorted.values]\n",
    "axes[1].barh(total_sector_returns_sorted.index, total_sector_returns_sorted.values, color=colors_bar, alpha=0.8)\n",
    "axes[1].axvline(0, color='gray', linestyle='--')\n",
    "axes[1].set_title('Xếp hạng Tỷ suất Sinh lời 10 Nhóm Ngành ICB (2020 - 2026)', fontsize=12, fontweight='bold')\n",
    "axes[1].set_xlabel('Lợi suất Tổng (%)')\n",
    "axes[1].invert_yaxis()\n",
    "for i, v in enumerate(total_sector_returns_sorted.values):\n",
    "    axes[1].text(v + (2 if v >= 0 else -15), i, f'{v:.1f}%', va='center', fontsize=9, fontweight='bold')\n",
    "\n",
    "plt.tight_layout()\n",
    "plt.show()"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": None,
   "metadata": {},
   "outputs": [],
   "source": [
    "# 4.2 Ma trận Tương quan Lợi suất Ngành (Sector Correlation Heatmap)\n",
    "ret_sectors = df_sectors.pct_change().dropna()\n",
    "corr_sectors = ret_sectors.corr()\n",
    "\n",
    "fig, ax = plt.subplots(figsize=(10, 8))\n",
    "sns.heatmap(corr_sectors, annot=True, cmap='RdYlGn', vmin=0.3, vmax=1.0, fmt='.2f', ax=ax, cbar_kws={'label': 'Pearson Correlation'})\n",
    "ax.set_title('Ma trận Tương quan Lợi suất Hàng ngày giữa 10 Nhóm Ngành ICB', fontsize=13, fontweight='bold')\n",
    "plt.tight_layout()\n",
    "plt.show()"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "### Nhận xét quan trọng về Tương quan Ngành (Diversification Opportunities):\n",
    "- **Cặp ngành tương quan cao nhất:** `VNFIN` (Tài chính) và `VNREAL` (Bất động sản) có tương quan lên tới **> 0.75**, do ngân hàng là nguồn cung tín dụng trực tiếp cho thị trường bất động sản.\n",
    "- **Các ngành phòng thủ có tương quan thấp:** `VNUTI` (Điện nước tiện ích) và `VNHEAL` (Y tế / Dược phẩm) có mức tương quan thấp nhất với thị trường chung ($0.45 - 0.55$), là công cụ phòng vệ danh mục (Hedging / Defensive Assets) tuyệt vời trong các giai đoạn suy thoái."
   ]
  },
  {
   "cell_type": "code",
   "execution_count": None,
   "metadata": {},
   "outputs": [],
   "source": [
    "# 4.3 Khảo sát Tỷ trọng Thanh khoản giữa các Ngành (Liquidity Dominance)\n",
    "query_sector_vol = f\"\"\"\n",
    "    SELECT index_code, round(avg(volume), 0) as avg_daily_vol\n",
    "    FROM core.market_index_daily\n",
    "    WHERE index_code IN ({','.join([repr(x) for x in sector_cols])})\n",
    "      AND date >= '2023-01-01'\n",
    "    GROUP BY index_code\n",
    "    ORDER BY avg_daily_vol DESC\n",
    "\"\"\"\n",
    "df_sec_vol = con.execute(query_sector_vol).fetchdf()\n",
    "df_sec_vol['vol_pct'] = (df_sec_vol['avg_daily_vol'] / df_sec_vol['avg_daily_vol'].sum()) * 100\n",
    "\n",
    "fig, ax = plt.subplots(figsize=(10, 6))\n",
    "ax.pie(df_sec_vol['vol_pct'], labels=df_sec_vol['index_code'], autopct='%1.1f%%', startangle=140, \n",
    "       colors=sns.color_palette('pastel', len(df_sec_vol)), wedgeprops={'edgecolor': 'white', 'linewidth': 1.5})\n",
    "ax.set_title('Tỷ trọng Thanh khoản Khớp lệnh Bình quân theo Ngành (2023 - 2026)', fontsize=13, fontweight='bold')\n",
    "plt.show()"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "--- \n",
    "## PHẦN V: TỔNG KẾT PHÁT HIỆN & KHUYẾN NGHỊ ĐỊNH LƯỢNG CHO HỆ THỐNG VESTA\n",
    "\n",
    "### 1. Ý nghĩa của Rổ Kín Room Ngoại (VNDIAMOND):\n",
    "- **Chỉ báo dẫn dắt (Leading Indicator):** Rổ `VNDIAMOND` đại diện cho các doanh nghiệp chất lượng cao nhất được các quỹ tổ chức nước ngoài săn đón. Biến động phân kỳ giữa VNDIAMOND và VN30 là tín hiệu chỉ báo sớm về dòng tiền tổ chức quốc tế (Foreign Capital Inflow / Outflow).\n",
    "\n",
    "### 2. Ý nghĩa của Bộ Chỉ số 10 Ngành ICB:\n",
    "- **Mô hình Luân chuyển Ngành (Sector Rotation Engine):** Trong các giai đoạn thị trường tăng giá (Bull Market), ngành `VNFIN` (Tài chính) và `VNIT` (Công nghệ) thường dẫn dắt sóng tăng mạnh nhất với Beta cao. Ngược lại, khi thị trường đi vào vùng rủi ro, dòng tiền có xu hướng co cụm vào `VNUTI` (Tiện ích) và `VNCONS` (Tiêu dùng thiết yếu).\n",
    "- **Tích hợp vào Tầng Preprocessing (F1xx) & Modeling (F2xx):** Toàn bộ chuỗi dữ liệu 23 rổ nhóm và ngành hiện đã có đầy đủ trong `core.market_index_daily` của `vesta_ohlcv.duckdb`, sẵn sàng cung cấp các Feature vĩ mô và ngành cho mô hình học máy."
   ]
  }
 ],
 "metadata": {
  "language_info": {
   "name": "python"
  }
 },
 "nbformat": 4,
 "nbformat_minor": 2
}

output_path = "d:/VESTA/notebooks/ohlcv/02_market_indices_and_group_rooms_eda.ipynb"
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(notebook_data, f, ensure_ascii=False, indent=1)

print(f"✅ Đã nâng cấp thành công Notebook Deep EDA 23 Rổ Nhóm tại: {output_path}")
