"""vesta_crawler_gui.py

VESTA QUANTITATIVE LAKEHOUSE — DESKTOP CRAWLER CONTROLLER (Windows GUI App)
Ứng dụng giao diện desktop đồ họa (Tkinter Native) tích hợp toàn diện hệ thống cào dữ liệu:
1. Bảng Dashboard kiểm tra trạng thái Lakehouse (min_date, max_date chuẩn không bị outlier tương lai, số lượng bản ghi, độ trễ).
2. Kiểm tra trùng lặp trước khi cào (Pre-flight Duplicate & Gap Check): Tự động kiểm tra URL/ngày nến đã có, chỉ cào dữ liệu mới.
3. Menu cấu hình động theo từng phân hệ (Dynamic Category Configuration): Mỗi loại dữ liệu có khung tùy chỉnh riêng biệt, sắp xếp gọn gàng.
4. Màn hình Console thời gian thực (Realtime Logging) đa luồng (Multi-threading), tương thích sys.stdout.reconfigure() không bao giờ văng lỗi.
"""

from __future__ import annotations

import datetime as dt
import io
import logging
import os
import pathlib
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Dict, List, Optional, Set, Tuple

import duckdb
import pandas as pd

# Định vị thư mục gốc dự án an toàn trong mọi trường hợp (gốc hoặc src/crawlers)
def find_project_root() -> pathlib.Path:
    p = pathlib.Path(__file__).resolve()
    for parent in [p.parent, *p.parents]:
        if (parent / "configs").exists() and (parent / "src").exists():
            return parent
    return pathlib.Path.cwd()

PROJECT_ROOT = find_project_root()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))
VENV_SITE = PROJECT_ROOT / ".venv" / "Lib" / "site-packages"
if VENV_SITE.exists() and str(VENV_SITE) not in sys.path:
    sys.path.insert(1, str(VENV_SITE))

try:
    from src.crawlers.db_writer import DEFAULT_TARGET_DB, ResilientDuckDBWriter
    from src.crawlers.track_crawling_progress import VN30_SYMBOLS
    from src.crawlers.vesta_crawler_cli import (
        CATEGORIES_REGISTRY,
        TABLE_METADATA_SPECS,
        get_target_symbols,
        run_latest_all,
    )
    from src.etl import db
except ImportError:
    from src.crawlers.db_writer import DEFAULT_TARGET_DB, ResilientDuckDBWriter
    from src.crawlers.track_crawling_progress import VN30_SYMBOLS
    from src.crawlers.vesta_crawler_cli import (
        CATEGORIES_REGISTRY,
        TABLE_METADATA_SPECS,
        get_target_symbols,
        run_latest_all,
    )
    from src.etl import db


# =============================================================================
# 1. TEXT REDIRECTOR AN TOÀN (TƯƠNG THÍCH ĐẦY ĐỦ SYS.STDOUT)
# =============================================================================

class SafeTextRedirector:
    """Bộ chuyển hướng luồng stdout/stderr vào widget Text của Tkinter.
    
    Hỗ trợ đầy đủ các thuộc tính file-like (reconfigure, flush, isatty, encoding)
    để không bao giờ bị lỗi 'TextRedirector object has no attribute reconfigure'.
    """

    def __init__(self, text_widget: tk.Text, tag: str = "stdout"):
        self.text_widget = text_widget
        self.tag = tag
        self.encoding = "utf-8"
        self.errors = "replace"

    def write(self, string: str):
        self.text_widget.after(0, self._append_text, string)

    def _append_text(self, string: str):
        try:
            self.text_widget.configure(state="normal")
            self.text_widget.insert("end", string, (self.tag,))
            self.text_widget.see("end")
            self.text_widget.configure(state="disabled")
        except Exception:
            pass

    def flush(self):
        pass

    def reconfigure(self, *args, **kwargs):
        """Tương thích tuyệt đối với sys.stdout.reconfigure(encoding='utf-8')."""
        pass

    def isatty(self) -> bool:
        return False

    def fileno(self):
        raise io.UnsupportedOperation("fileno not supported on SafeTextRedirector")


# =============================================================================
# 2. CỬA SỔ ỨNG DỤNG CHÍNH (VESTA CRAWLER APP)
# =============================================================================

class VestaCrawlerApp(tk.Tk):
    """Giao diện điều phối cào dữ liệu VESTA Lakehouse."""

    def __init__(self):
        super().__init__()

        self.title("VESTA Quantitative Lakehouse — Desktop Crawler Controller")
        self.geometry("1220x840")
        self.minsize(1080, 740)

        self.target_db = DEFAULT_TARGET_DB
        self.crawler_thread: Optional[threading.Thread] = None
        self.is_running = False

        self._configure_styles()
        self._build_ui()
        self._redirect_logs()

        # Tự động tải trạng thái ban đầu
        self.after(250, self.refresh_status_async)

    def _configure_styles(self):
        self.style = ttk.Style(self)
        self.style.theme_use("clam")

        self.bg_main = "#f4f6f9"
        self.bg_card = "#ffffff"
        self.color_primary = "#1d4ed8"
        self.color_success = "#16a34a"
        self.color_danger = "#dc2626"
        self.color_text = "#1e293b"
        self.color_text_muted = "#64748b"

        self.configure(bg=self.bg_main)
        self.style.configure(".", background=self.bg_main, foreground=self.color_text, font=("Segoe UI", 10))
        self.style.configure("Card.TFrame", background=self.bg_card, relief="flat")
        self.style.configure("Header.TLabel", font=("Segoe UI", 15, "bold"), foreground=self.color_primary, background=self.bg_main)
        self.style.configure("SubHeader.TLabel", font=("Segoe UI", 9), foreground=self.color_text_muted, background=self.bg_main)
        self.style.configure("Section.TLabel", font=("Segoe UI", 11, "bold"), foreground=self.color_text, background=self.bg_card)

        # Buttons
        self.style.configure("Primary.TButton", font=("Segoe UI", 9, "bold"), background=self.color_primary, foreground="#ffffff", padding=5)
        self.style.map("Primary.TButton", background=[("active", "#1e40af"), ("disabled", "#94a3b8")])

        self.style.configure("Success.TButton", font=("Segoe UI", 10, "bold"), background=self.color_success, foreground="#ffffff", padding=8)
        self.style.map("Success.TButton", background=[("active", "#15803d"), ("disabled", "#94a3b8")])

        self.style.configure("Danger.TButton", font=("Segoe UI", 10, "bold"), background=self.color_danger, foreground="#ffffff", padding=8)
        self.style.map("Danger.TButton", background=[("active", "#b91c1c"), ("disabled", "#94a3b8")])

        # Treeview
        self.style.configure(
            "Treeview",
            background="#ffffff",
            foreground=self.color_text,
            rowheight=26,
            fieldbackground="#ffffff",
            font=("Segoe UI", 9),
        )
        self.style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"), background="#e2e8f0", foreground=self.color_text)
        self.style.map("Treeview", background=[("selected", "#dbeafe")], foreground=[("selected", "#1e40af")])

    def _build_ui(self):
        # 1. HEADER
        header_frame = ttk.Frame(self, padding=(16, 10, 16, 6))
        header_frame.pack(fill="x")

        title_box = ttk.Frame(header_frame)
        title_box.pack(side="left", fill="y")
        ttk.Label(title_box, text="VESTA QUANT LAKEHOUSE — CRAWLER CONTROLLER", style="Header.TLabel").pack(anchor="w")
        db_name = os.path.basename(self.target_db)
        self.lbl_subtitle = ttk.Label(title_box, text=f"CSDL: {db_name} | Bộ đệm: Sạch | Vnstock Sponsor Unified API | T-0: {dt.date.today()}", style="SubHeader.TLabel")
        self.lbl_subtitle.pack(anchor="w")

        self.btn_refresh = ttk.Button(header_frame, text="🔄 Làm Mới Trạng Thái", command=self.refresh_status_async, style="Primary.TButton")
        self.btn_refresh.pack(side="right", pady=4)

        self.btn_sync = ttk.Button(header_frame, text="⚡ Đồng Bộ Bộ Đệm", command=self.sync_buffer_async, style="Primary.TButton")
        self.btn_sync.pack(side="right", padx=(0, 6), pady=4)

        # 2. KHUNG CHÍNH (PanedWindow chia trên - dưới)
        main_paned = ttk.PanedWindow(self, orient="vertical")
        main_paned.pack(fill="both", expand=True, padx=16, pady=(0, 10))

        # --- NỬA TRÊN: STATUS TABLE + DYNAMIC CONFIG CARD ---
        top_container = ttk.Frame(main_paned)
        main_paned.add(top_container, weight=4)

        # Cột trái (60%): Bảng trạng thái
        status_card = ttk.Frame(top_container, style="Card.TFrame", padding=10)
        status_card.pack(side="left", fill="both", expand=True, padx=(0, 8))

        ttk.Label(status_card, text="TÌNH TRẠNG DỮ LIỆU LAKEHOUSE (LỌC BỎ OUTLIER > HÔM NAY)", style="Section.TLabel").pack(anchor="w", pady=(0, 6))

        tree_cols = ("table", "records", "symbols", "min_date", "max_date", "status")
        self.tree_status = ttk.Treeview(status_card, columns=tree_cols, show="headings", height=11)
        self.tree_status.heading("table", text="Phân Hệ / Bảng")
        self.tree_status.heading("records", text="Số Bản Ghi")
        self.tree_status.heading("symbols", text="Số Mã")
        self.tree_status.heading("min_date", text="Min Date")
        self.tree_status.heading("max_date", text="Max Date (<= Nay)")
        self.tree_status.heading("status", text="Độ Trễ / Tình Trạng")

        self.tree_status.column("table", width=210, anchor="w")
        self.tree_status.column("records", width=95, anchor="e")
        self.tree_status.column("symbols", width=65, anchor="center")
        self.tree_status.column("min_date", width=90, anchor="center")
        self.tree_status.column("max_date", width=95, anchor="center")
        self.tree_status.column("status", width=145, anchor="w")

        tree_scroll_y = ttk.Scrollbar(status_card, orient="vertical", command=self.tree_status.yview)
        self.tree_status.configure(yscrollcommand=tree_scroll_y.set)
        self.tree_status.pack(side="left", fill="both", expand=True)
        tree_scroll_y.pack(side="right", fill="y")

        # Cột phải (40%): Cấu hình cào ĐỘNG THEO TỪNG PHÂN HỆ
        self.ctrl_card = ttk.Frame(top_container, style="Card.TFrame", padding=12)
        self.ctrl_card.pack(side="right", fill="both", expand=False, ipadx=4)

        ttk.Label(self.ctrl_card, text="CẤU HÌNH & ĐIỀU PHỐI CÀO CHI TIẾT", style="Section.TLabel").pack(anchor="w", pady=(0, 6))

        # Chọn chế độ
        mode_box = ttk.Frame(self.ctrl_card, style="Card.TFrame")
        mode_box.pack(fill="x", pady=2)
        self.var_mode = tk.StringVar(value="category")
        ttk.Radiobutton(mode_box, text="Theo Phân Hệ Chọn Lọc (Category)", value="category", variable=self.var_mode, command=self._on_mode_or_category_change).pack(anchor="w")
        ttk.Radiobutton(mode_box, text="Cập Nhật Mới Nhất (Latest Catch-up)", value="latest", variable=self.var_mode, command=self._on_mode_or_category_change).pack(anchor="w")
        ttk.Radiobutton(mode_box, text="Cào Toàn Bộ Danh Mục (All Categories)", value="all", variable=self.var_mode, command=self._on_mode_or_category_change).pack(anchor="w")

        # Dropdown phân hệ
        self.lbl_cat = ttk.Label(self.ctrl_card, text="Lựa chọn phân hệ cần cào:", font=("Segoe UI", 9, "bold"))
        self.lbl_cat.pack(anchor="w", pady=(6, 2))

        self.cat_map = {
            "ohlcv": "1. Giá nến ngày / phút (OHLCV)",
            "fundamentals": "2. Báo cáo tài chính (BCTC)",
            "news_macro": "3. Báo chí Vĩ mô (Nhân Dân, TBTC, VNF, Chính Phủ)",
            "news": "4. Tin tức doanh nghiệp CafeF theo mã",
            "events": "5. Lịch sự kiện doanh nghiệp & Cổ tức",
            "macro": "6. 9 Chỉ số vĩ mô & Lãi suất LH",
            "governance": "7. Hồ sơ doanh nghiệp & Cổ đông lớn",
        }
        self.combo_cat = ttk.Combobox(self.ctrl_card, values=list(self.cat_map.values()), state="readonly")
        self.combo_cat.current(0)
        self.combo_cat.pack(fill="x", pady=2)
        self.combo_cat.bind("<<ComboboxSelected>>", lambda e: self._on_mode_or_category_change())

        ttk.Separator(self.ctrl_card, orient="horizontal").pack(fill="x", pady=8)

        # KHUNG CẤU HÌNH ĐỘNG (Dynamic Config Sub-frames)
        self.dynamic_config_container = ttk.Frame(self.ctrl_card, style="Card.TFrame")
        self.dynamic_config_container.pack(fill="both", expand=True)

        self._init_category_frames()
        self._show_active_config_frame()

        # Nút thực thi chính
        btn_box = ttk.Frame(self.ctrl_card, style="Card.TFrame")
        btn_box.pack(fill="x", pady=(8, 0))

        self.btn_start = ttk.Button(btn_box, text="BẮT ĐẦU CÀO DỮ LIỆU", style="Success.TButton", command=self.start_crawl_thread)
        self.btn_start.pack(fill="x", pady=2)

        self.btn_stop = ttk.Button(btn_box, text="DỪNG TIẾN TRÌNH", style="Danger.TButton", command=self.stop_crawl, state="disabled")
        self.btn_stop.pack(fill="x", pady=2)

        # --- NỬA DƯỚI: REALTIME LOG VIEWER ---
        log_card = ttk.Frame(main_paned, style="Card.TFrame", padding=10)
        main_paned.add(log_card, weight=3)

        log_header = ttk.Frame(log_card, style="Card.TFrame")
        log_header.pack(fill="x", pady=(0, 4))
        ttk.Label(log_header, text="MÀN HÌNH THEO DÕI TIẾN TRÌNH THỜI GIAN THỰC (CONSOLE OUTPUT)", style="Section.TLabel").pack(side="left")
        ttk.Button(log_header, text="Xóa Log", command=self.clear_logs).pack(side="right")

        self.txt_log = tk.Text(
            log_card,
            wrap="word",
            bg="#0f172a",
            fg="#f8fafc",
            insertbackground="#ffffff",
            font=("Consolas", 10),
            state="disabled",
            relief="flat",
        )
        log_scroll = ttk.Scrollbar(log_card, orient="vertical", command=self.txt_log.yview)
        self.txt_log.configure(yscrollcommand=log_scroll.set)

        self.txt_log.pack(side="left", fill="both", expand=True)
        log_scroll.pack(side="right", fill="y")

        self.txt_log.tag_configure("stdout", foreground="#f8fafc")
        self.txt_log.tag_configure("stderr", foreground="#f87171")

    def _init_category_frames(self):
        """Khởi tạo các khung cấu hình chuyên biệt cho từng loại dữ liệu."""
        self.frames = {}

        # 1. Khung cấu hình OHLCV
        f_ohlcv = ttk.Frame(self.dynamic_config_container, style="Card.TFrame")
        self.frames["ohlcv"] = f_ohlcv
        ttk.Label(f_ohlcv, text="Cấu hình Giá Nến (OHLCV):", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 4))

        self.var_ohlcv_interval = tk.StringVar(value="1D")
        f_int = ttk.Frame(f_ohlcv, style="Card.TFrame")
        f_int.pack(fill="x", pady=2)
        ttk.Label(f_int, text="Khung nến:").pack(side="left")
        ttk.Combobox(f_int, textvariable=self.var_ohlcv_interval, values=["1D", "1m"], width=6, state="readonly").pack(side="left", padx=6)

        self.var_ohlcv_symbols = tk.StringVar(value="all")
        ttk.Label(f_ohlcv, text="Mã cổ phiếu:").pack(anchor="w", pady=(4, 1))
        ttk.Entry(f_ohlcv, textvariable=self.var_ohlcv_symbols).pack(fill="x", pady=2)
        
        q_sym = ttk.Frame(f_ohlcv, style="Card.TFrame")
        q_sym.pack(fill="x", pady=2)
        ttk.Button(q_sym, text="Tất cả (1,522)", command=lambda: self.var_ohlcv_symbols.set("all")).pack(side="left", padx=(0, 2))
        ttk.Button(q_sym, text="VN30", command=lambda: self.var_ohlcv_symbols.set("vn30")).pack(side="left", padx=2)
        ttk.Button(q_sym, text="Top 3", command=lambda: self.var_ohlcv_symbols.set("VCB,FPT,HPG")).pack(side="left", padx=2)

        self.var_ohlcv_delay = tk.DoubleVar(value=0.4)
        f_del = ttk.Frame(f_ohlcv, style="Card.TFrame")
        f_del.pack(fill="x", pady=2)
        ttk.Label(f_del, text="Độ trễ (Delay s):").pack(side="left")
        ttk.Spinbox(f_del, from_=0.1, to=5.0, increment=0.1, textvariable=self.var_ohlcv_delay, width=6).pack(side="left", padx=6)

        self.var_ohlcv_force = tk.BooleanVar(value=False)
        ttk.Checkbutton(f_ohlcv, text="Cào đè lại toàn bộ (--force)", variable=self.var_ohlcv_force).pack(anchor="w", pady=4)

        # 2. Khung cấu hình FUNDAMENTALS
        f_fund = ttk.Frame(self.dynamic_config_container, style="Card.TFrame")
        self.frames["fundamentals"] = f_fund
        ttk.Label(f_fund, text="Cấu hình Báo Cáo Tài Chính (BCTC):", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 4))

        self.var_fund_period = tk.StringVar(value="quarter")
        f_per = ttk.Frame(f_fund, style="Card.TFrame")
        f_per.pack(fill="x", pady=2)
        ttk.Label(f_per, text="Kỳ báo cáo:").pack(side="left")
        ttk.Combobox(f_per, textvariable=self.var_fund_period, values=["quarter", "year"], width=8, state="readonly").pack(side="left", padx=6)

        self.var_fund_report = tk.StringVar(value="all")
        f_rep = ttk.Frame(f_fund, style="Card.TFrame")
        f_rep.pack(fill="x", pady=2)
        ttk.Label(f_rep, text="Loại báo cáo:").pack(side="left")
        ttk.Combobox(f_rep, textvariable=self.var_fund_report, values=["all", "balance_sheet", "income_statement", "cash_flow", "ratio"], width=14, state="readonly").pack(side="left", padx=6)

        self.var_fund_symbols = tk.StringVar(value="all")
        ttk.Label(f_fund, text="Mã cổ phiếu:").pack(anchor="w", pady=(4, 1))
        ttk.Entry(f_fund, textvariable=self.var_fund_symbols).pack(fill="x", pady=2)

        self.var_fund_delay = tk.DoubleVar(value=0.4)
        f_fdel = ttk.Frame(f_fund, style="Card.TFrame")
        f_fdel.pack(fill="x", pady=2)
        ttk.Label(f_fdel, text="Độ trễ (Delay s):").pack(side="left")
        ttk.Spinbox(f_fdel, from_=0.1, to=5.0, increment=0.1, textvariable=self.var_fund_delay, width=6).pack(side="left", padx=6)

        # 3. Khung cấu hình NEWS_MACRO (BÁO CHÍ VĨ MÔ)
        f_nmacro = ttk.Frame(self.dynamic_config_container, style="Card.TFrame")
        self.frames["news_macro"] = f_nmacro
        ttk.Label(f_nmacro, text="Cấu hình 4 Kênh Báo Chí Vĩ Mô:", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 4))

        self.var_nmacro_source = tk.StringVar(value="all")
        f_src = ttk.Frame(f_nmacro, style="Card.TFrame")
        f_src.pack(fill="x", pady=2)
        ttk.Label(f_src, text="Nguồn báo:").pack(side="left")
        ttk.Combobox(f_src, textvariable=self.var_nmacro_source, values=["all", "nhandan", "baochinhphu", "thoibaotaichinh", "vietnamfinance"], width=14, state="readonly").pack(side="left", padx=6)

        self.var_nmacro_pages = tk.IntVar(value=10)
        f_pgs = ttk.Frame(f_nmacro, style="Card.TFrame")
        f_pgs.pack(fill="x", pady=2)
        ttk.Label(f_pgs, text="Số trang / đợt:").pack(side="left")
        ttk.Spinbox(f_pgs, from_=1, to=100, textvariable=self.var_nmacro_pages, width=6).pack(side="left", padx=6)

        self.var_nmacro_dedup = tk.BooleanVar(value=True)
        ttk.Checkbutton(f_nmacro, text="Tự động bỏ qua tin bài đã có (Check Dup)", variable=self.var_nmacro_dedup).pack(anchor="w", pady=4)
        ttk.Label(f_nmacro, text="* Tin bài có ngày công bố > hôm nay sẽ tự động bị loại bỏ.", font=("Segoe UI", 8), foreground=self.color_text_muted).pack(anchor="w")

        # 4. Khung cấu hình NEWS (TIN DOANH NGHIỆP CAFEF)
        f_news = ttk.Frame(self.dynamic_config_container, style="Card.TFrame")
        self.frames["news"] = f_news
        ttk.Label(f_news, text="Cấu hình Tin Tức CafeF theo mã:", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 4))

        self.var_news_symbols = tk.StringVar(value="vn30")
        ttk.Label(f_news, text="Mã cổ phiếu:").pack(anchor="w", pady=(2, 1))
        ttk.Entry(f_news, textvariable=self.var_news_symbols).pack(fill="x", pady=2)

        self.var_news_delay = tk.DoubleVar(value=0.5)
        f_ndel = ttk.Frame(f_news, style="Card.TFrame")
        f_ndel.pack(fill="x", pady=2)
        ttk.Label(f_ndel, text="Độ trễ:").pack(side="left")
        ttk.Spinbox(f_ndel, from_=0.2, to=3.0, increment=0.1, textvariable=self.var_news_delay, width=6).pack(side="left", padx=6)

        self.var_news_force = tk.BooleanVar(value=False)
        ttk.Checkbutton(f_news, text="Cào lại toàn bộ lịch sử từ 2007 (--force)", variable=self.var_news_force).pack(anchor="w", pady=2)
        ttk.Label(f_news, text="* Mặc định: Tự động dừng ngay khi gặp tin cũ (chỉ cào bù các ngày còn thiếu).", font=("Segoe UI", 8), foreground=self.color_text_muted).pack(anchor="w")

        # 5. Khung cấu hình MACRO & LÃI SUẤT
        f_macro = ttk.Frame(self.dynamic_config_container, style="Card.TFrame")
        self.frames["macro"] = f_macro
        ttk.Label(f_macro, text="Cấu hình Vĩ mô & Lãi suất:", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 4))
        self.var_macro_9ind = tk.BooleanVar(value=True)
        ttk.Checkbutton(f_macro, text="9 Chỉ số vĩ mô (GDP, CPI, FDI, XNK...)", variable=self.var_macro_9ind).pack(anchor="w", pady=2)
        self.var_macro_rates = tk.BooleanVar(value=True)
        ttk.Checkbutton(f_macro, text="Lãi suất liên ngân hàng & Lợi suất TPCP VN10Y", variable=self.var_macro_rates).pack(anchor="w", pady=2)

        # 6. Khung cấu hình EVENTS
        f_events = ttk.Frame(self.dynamic_config_container, style="Card.TFrame")
        self.frames["events"] = f_events
        ttk.Label(f_events, text="Cấu hình Lịch Sự Kiện & Cổ Tức:", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 4))
        self.var_events_symbols = tk.StringVar(value="all")
        ttk.Label(f_events, text="Mã cổ phiếu:").pack(anchor="w")
        ttk.Entry(f_events, textvariable=self.var_events_symbols).pack(fill="x", pady=2)

        # 7. Khung cấu hình GOVERNANCE
        f_gov = ttk.Frame(self.dynamic_config_container, style="Card.TFrame")
        self.frames["governance"] = f_gov
        ttk.Label(f_gov, text="Cấu hình Hồ Sơ & Cổ Đông Lớn:", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 4))
        self.var_gov_symbols = tk.StringVar(value="vn30")
        ttk.Label(f_gov, text="Mã cổ phiếu:").pack(anchor="w")
        ttk.Entry(f_gov, textvariable=self.var_gov_symbols).pack(fill="x", pady=2)

        # 8. Khung LATEST (Cào bù toàn bộ đến hôm nay)
        f_latest = ttk.Frame(self.dynamic_config_container, style="Card.TFrame")
        self.frames["latest"] = f_latest
        ttk.Label(f_latest, text="Cập Nhật Mới Nhất Toàn Bộ Thị Trường:", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 4))
        ttk.Label(f_latest, text="Tự động phát hiện ngày cào cuối (max_date) và cào bù\ntiến đến hôm nay cho tất cả phân hệ.", font=("Segoe UI", 8), foreground=self.color_text_muted).pack(anchor="w")

        self.var_latest_symbols = tk.StringVar(value="all")
        ttk.Label(f_latest, text="Danh mục mã:").pack(anchor="w", pady=(4, 1))
        ttk.Entry(f_latest, textvariable=self.var_latest_symbols).pack(fill="x", pady=2)
        
        q_lsym = ttk.Frame(f_latest, style="Card.TFrame")
        q_lsym.pack(fill="x", pady=2)
        ttk.Button(q_lsym, text="Toàn bộ", command=lambda: self.var_latest_symbols.set("all")).pack(side="left", padx=(0, 2))
        ttk.Button(q_lsym, text="VN30", command=lambda: self.var_latest_symbols.set("vn30")).pack(side="left", padx=2)

    def _get_active_cat_key(self) -> str:
        selected_display = self.combo_cat.get()
        for k, v in self.cat_map.items():
            if v == selected_display:
                return k
        return "ohlcv"

    def _on_mode_or_category_change(self):
        mode = self.var_mode.get()
        if mode == "category":
            self.combo_cat.configure(state="readonly")
            self._show_active_config_frame()
        elif mode == "latest":
            self.combo_cat.configure(state="disabled")
            self._hide_all_frames()
            self.frames["latest"].pack(fill="both", expand=True)
        else:
            self.combo_cat.configure(state="disabled")
            self._hide_all_frames()

    def _hide_all_frames(self):
        for f in self.frames.values():
            f.pack_forget()

    def _show_active_config_frame(self):
        self._hide_all_frames()
        cat_key = self._get_active_cat_key()
        if cat_key in self.frames:
            self.frames[cat_key].pack(fill="both", expand=True)

    def _redirect_logs(self):
        self.redirector_out = SafeTextRedirector(self.txt_log, tag="stdout")
        self.redirector_err = SafeTextRedirector(self.txt_log, tag="stderr")
        sys.stdout = self.redirector_out
        sys.stderr = self.redirector_err

    def clear_logs(self):
        self.txt_log.configure(state="normal")
        self.txt_log.delete("1.0", "end")
        self.txt_log.configure(state="disabled")

    # =========================================================================
    # 3. QUÉT TRẠNG THÁI LAKEHOUSE (LỌC BỎ OUTLIER TƯƠNG LAI)
    # =========================================================================

    def refresh_status_async(self):
        self.btn_refresh.configure(state="disabled", text="⏳ Đang quét...")
        threading.Thread(target=self._worker_refresh_status, daemon=True).start()

    def _worker_refresh_status(self):
        today = dt.date.today()
        rows_data = []

        try:
            con = duckdb.connect(self.target_db, read_only=True)
        except Exception:
            buf_db = str(PROJECT_ROOT / "db" / "vesta_crawled_fresh.duckdb")
            if os.path.exists(buf_db):
                try:
                    con = duckdb.connect(buf_db, read_only=True)
                except Exception:
                    con = None
            else:
                con = None

        if con is None:
            self.after(0, self._finish_refresh_status, [], "Không thể kết nối database (bị khóa hoặc không tồn tại)")
            return

        try:
            for spec in TABLE_METADATA_SPECS:
                tbl = spec["table"]
                name = spec["name"]
                date_col = spec["date_col"]
                sym_col = spec["sym_col"]

                schema, table_name = tbl.split(".")
                tbl_exists = con.execute(
                    "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = ? AND table_name = ?",
                    [schema, table_name],
                ).fetchone()[0]

                if not tbl_exists:
                    rows_data.append((name, "-", "-", "-", "-", "Chưa khởi tạo"))
                    continue

                sym_expr = f"COUNT(DISTINCT {sym_col})" if sym_col else "'-'"
                
                # LỌC BỎ OUTLIER TƯƠNG LAI (> TODAY) VÀ CỔ ĐẠI (< 2000) KHI ĐO MAX/MIN
                if "corporate_events" in tbl:
                    date_expr = f"CAST(MIN({date_col}) AS VARCHAR), CAST(MAX({date_col}) AS VARCHAR)"
                else:
                    date_expr = f"""
                        CAST(MIN(CASE WHEN {date_col} >= '2000-01-01' THEN {date_col} ELSE NULL END) AS VARCHAR),
                        CAST(MAX(CASE WHEN {date_col} <= CURRENT_DATE THEN {date_col} ELSE NULL END) AS VARCHAR)
                    """

                row = con.execute(f"SELECT COUNT(*), {sym_expr}, {date_expr} FROM {tbl}").fetchone()

                total_rows = row[0]
                total_syms = row[1] if row[1] != "-" else "-"
                min_date = str(row[2])[:10] if row[2] else "-"
                max_date = str(row[3])[:10] if row[3] else "-"

                status_desc = "Trống"
                if total_rows > 0 and max_date != "-":
                    try:
                        max_d = dt.date.fromisoformat(max_date)
                        gap_days = (today - max_d).days
                        if gap_days <= 1:
                            status_desc = "✅ Rất mới (T-0/T-1)"
                        elif gap_days <= 7:
                            status_desc = f"⚠️ Trễ {gap_days} ngày"
                        elif gap_days <= 95:
                            status_desc = f"⚠️ Trễ {gap_days // 30} tháng"
                        else:
                            status_desc = f"❌ Cần cào bù ({gap_days}d)"
                    except Exception:
                        status_desc = "Đã có dữ liệu"

                rows_data.append((name, f"{total_rows:,}", str(total_syms), min_date, max_date, status_desc))
            con.close()

            # Kiểm tra dữ liệu trong buffer_db (nếu có)
            buf_db = str(PROJECT_ROOT / "db" / "vesta_crawled_fresh.duckdb")
            buf_info = "Bộ đệm: Sạch"
            if os.path.exists(buf_db):
                try:
                    con_b = duckdb.connect(buf_db, read_only=True)
                    b_rows = con_b.execute("SELECT schema_name, table_name FROM duckdb_tables() WHERE database_name = 'vesta_crawled_fresh' AND schema_name IN ('core', 'main')").fetchall()
                    b_cnt = 0
                    for s, t in b_rows:
                        b_cnt += con_b.execute(f"SELECT COUNT(1) FROM {s}.{t}").fetchone()[0]
                    con_b.close()
                    if b_cnt > 0:
                        buf_info = f"⚡ Bộ đệm: Có {b_cnt:,} bản ghi"
                except Exception:
                    pass

            self.after(0, self._finish_refresh_status, rows_data, None, buf_info)
        except Exception as ex:
            if con:
                con.close()
            self.after(0, self._finish_refresh_status, [], str(ex), "Bộ đệm: Chưa xác định")

    def _finish_refresh_status(self, rows: List[tuple], error: Optional[str], buf_info: str = "Bộ đệm: Sạch"):
        self.btn_refresh.configure(state="normal", text="🔄 Làm Mới Trạng Thái")
        if hasattr(self, "lbl_subtitle"):
            db_name = os.path.basename(self.target_db)
            self.lbl_subtitle.configure(text=f"CSDL: {db_name} | {buf_info} | Vnstock Sponsor Unified API | T-0: {dt.date.today()}")

        if error:
            messagebox.showwarning("Cảnh báo Database", f"Lỗi quét trạng thái: {error}")
            return

        for item in self.tree_status.get_children():
            self.tree_status.delete(item)

        for r in rows:
            self.tree_status.insert("", "end", values=r)

    def sync_buffer_async(self):
        self.btn_sync.configure(state="disabled", text="Đang đồng bộ...")
        threading.Thread(target=self._worker_sync_buffer, daemon=True).start()

    def _worker_sync_buffer(self):
        writer = ResilientDuckDBWriter(target_db=self.target_db)
        try:
            total = writer.sync_buffer_to_target()
            print(f"\n[⚡ ĐỒNG BỘ BỘ ĐỆM] Đã đồng bộ thành công +{total} bảng từ bộ đệm vào {os.path.basename(self.target_db)}.")
        except Exception as e:
            print(f"\n[!] Lỗi khi đồng bộ bộ đệm: {e}")
        self.after(0, self._finish_sync_buffer)

    def _finish_sync_buffer(self):
        self.btn_sync.configure(state="normal", text="Đồng Bộ Bộ Đệm")
        self.refresh_status_async()

    # =========================================================================
    # 4. PRE-CRAWL DUPLICATION & GAP CHECK (KIỂM TRA TRÙNG LẶP TRƯỚC KHI CÀO)
    # =========================================================================

    def _precheck_and_log(self, cat_key: str, symbols: List[str], target_db: str, force: bool) -> Dict[str, Any]:
        """Kiểm tra độ phủ và trùng lặp trước khi thực thi để tránh cào lại dữ liệu đã có."""
        today_str = dt.date.today().isoformat()
        print("\n" + "─" * 80)
        print(f"[*] TIẾN HÀNH PRE-CHECK & DEDUPLICATION CHO PHÂN HỆ: [{cat_key.upper()}]")
        
        precheck_res = {"existing_urls": set(), "symbols_to_crawl": symbols, "symbols_skipped": []}

        try:
            con = duckdb.connect(target_db, read_only=True)
        except Exception:
            con = None

        if con is None:
            print("  -> Không thể mở kết nối read_only. Bỏ qua pre-check, chạy mặc định.")
            return precheck_res

        try:
            # 1. Kiểm tra trùng lặp tin tức (News & News Macro)
            if cat_key in ("news_macro", "news"):
                tbl = "core.news_resources" if cat_key == "news_macro" else "core.news"
                existing_cnt = con.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
                rows = con.execute(f"SELECT source_url FROM {tbl} WHERE source_url IS NOT NULL").fetchall()
                precheck_res["existing_urls"] = {r[0] for r in rows}
                print(f"  -> Đã tìm thấy {existing_cnt:,} tin bài hiện có trong {tbl}.")
                print(f"  -> CƠ CHẾ: Đã nạp {len(precheck_res['existing_urls']):,} URLs vào bộ nhớ đệm.")
                print(f"  -> Toàn bộ tin bài đã có sẽ được BỎ QUA NGAY LẬP TỨC. Chỉ cào và lưu các tin bài mới!")

            # 2. Kiểm tra ngày nến OHLCV (Bỏ qua mã đã có đủ nến đến hôm nay)
            elif cat_key == "ohlcv":
                if force:
                    print("  -> Cờ --force được BẬT: Bỏ qua kiểm tra độ phủ, cào đè toàn bộ.")
                else:
                    sym_list = "', '".join([s.upper() for s in symbols])
                    query = f"""
                        SELECT upper(symbol), COUNT(*), MAX(date)
                        FROM core.market_ohlcv_daily
                        WHERE upper(symbol) IN ('{sym_list}')
                        GROUP BY symbol
                    """
                    rows = con.execute(query).fetchall()
                    to_crawl = []
                    skipped = []
                    for sym, cnt, max_d in rows:
                        max_str = str(max_d)[:10] if max_d else ""
                        if max_str >= today_str:
                            skipped.append(sym)
                        else:
                            to_crawl.append(sym)

                    # Thêm các mã chưa từng có dữ liệu
                    existing_set = {r[0] for r in rows}
                    for s in symbols:
                        if s.upper() not in existing_set:
                            to_crawl.append(s.upper())

                    precheck_res["symbols_to_crawl"] = to_crawl
                    precheck_res["symbols_skipped"] = skipped
                    print(f"  -> Đã kiểm tra {len(symbols)} mã trong core.market_ohlcv_daily:")
                    print(f"     • {len(skipped)} mã đã có đủ nến đến hôm nay ({today_str}) -> TỰ ĐỘNG BỎ QUA.")
                    print(f"     • {len(to_crawl)} mã còn thiếu dữ liệu -> SẼ ĐƯỢC CÀO BÙ TIẾN.")

            con.close()
        except Exception as e:
            if con:
                con.close()
            print(f"  -> [Cảnh báo] Lỗi trong lúc pre-check: {e}")

        print("─" * 80 + "\n")
        return precheck_res

    # =========================================================================
    # 5. ĐIỀU PHỐI VÀ CHẠY CRAWLER
    # =========================================================================

    def start_crawl_thread(self):
        if self.is_running:
            return

        self.is_running = True
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.btn_refresh.configure(state="disabled")

        self.crawler_thread = threading.Thread(target=self._worker_crawl, daemon=True)
        self.crawler_thread.start()

    def stop_crawl(self):
        if messagebox.askyesno("Xác nhận", "Bạn có chắc chắn muốn dừng tiến trình cào dữ liệu?"):
            self.is_running = False
            print("\n[!] Đã nhận lệnh dừng từ người dùng. Tiến trình sẽ dừng sau khi kết thúc lượt hiện tại...")

    def _worker_crawl(self):
        start_time = time.time()
        mode = self.var_mode.get()
        target_db = os.path.abspath(self.target_db)
        os.environ["VESTA_DB_PATH"] = target_db
        db.DB_PATH = pathlib.Path(target_db)
        writer = ResilientDuckDBWriter(target_db=target_db)

        # Dummy Args
        class CrawlArgs:
            pass
        args = CrawlArgs()
        args.db = target_db
        args.limit = None

        print("\n" + "═" * 80)
        print(f"KHỞI CHẠY TIẾN TRÌNH CÀO DỮ LIỆU — VESTA QUANT DESKTOP ({dt.datetime.now().strftime('%H:%M:%S')})")
        print(f"Chế độ: {mode.upper()} | Database đích: {os.path.basename(target_db)}")
        print("═" * 80)

        try:
            if mode == "latest":
                symbols_str = self.var_latest_symbols.get().strip()
                symbols = get_target_symbols(target_db, symbol_arg=symbols_str)
                args.symbols = symbols_str
                args.delay = 0.4
                args.interval = "1D"
                args.force = False
                args.period = "quarter"
                args.report_type = "all"
                args.pages = 3
                
                # Pre-check cho latest
                self._precheck_and_log("ohlcv", symbols, target_db, force=False)
                run_latest_all(symbols, writer, args)

            elif mode == "category":
                cat_key = self._get_active_cat_key()

                # Lấy tham số theo category
                if cat_key == "ohlcv":
                    symbols_str = self.var_ohlcv_symbols.get().strip()
                    args.interval = self.var_ohlcv_interval.get()
                    args.delay = float(self.var_ohlcv_delay.get())
                    args.force = self.var_ohlcv_force.get()
                    args.start = "2000-01-01"
                    args.end = None
                elif cat_key == "fundamentals":
                    symbols_str = self.var_fund_symbols.get().strip()
                    args.period = self.var_fund_period.get()
                    args.report_type = self.var_fund_report.get()
                    args.delay = float(self.var_fund_delay.get())
                    args.force = False
                elif cat_key == "news_macro":
                    symbols_str = "all"
                    args.source = self.var_nmacro_source.get()
                    args.pages = int(self.var_nmacro_pages.get())
                    args.delay = 0.5
                    args.force = False
                elif cat_key == "news":
                    symbols_str = self.var_news_symbols.get().strip()
                    args.delay = float(self.var_news_delay.get())
                    args.force = self.var_news_force.get()
                elif cat_key == "events":
                    symbols_str = self.var_events_symbols.get().strip()
                    args.delay = 0.4
                    args.force = False
                elif cat_key == "governance":
                    symbols_str = self.var_gov_symbols.get().strip()
                    args.delay = 0.3
                    args.force = False
                else: # macro
                    symbols_str = "all"
                    args.macro_9ind = self.var_macro_9ind.get()
                    args.macro_rates = self.var_macro_rates.get()
                    args.delay = 0.4
                    args.force = False

                symbols = get_target_symbols(target_db, symbol_arg=symbols_str)

                # THỰC HIỆN PRE-CHECK TRƯỚC KHI CÀO
                precheck = self._precheck_and_log(cat_key, symbols, target_db, force=getattr(args, "force", False))
                if cat_key == "ohlcv" and not getattr(args, "force", False):
                    symbols = precheck["symbols_to_crawl"]

                if not symbols and cat_key == "ohlcv":
                    print("[OK] Toàn bộ các mã đã có đầy đủ dữ liệu mới nhất. Không cần cào thêm!")
                else:
                    runner = CATEGORIES_REGISTRY[cat_key]
                    cnt = runner(symbols, writer, args)
                    writer.sync_buffer_to_target()
                    print(f"\n[OK] Hoàn tất phân hệ [{cat_key.upper()}]. Đã lưu thành công +{cnt:,} bản ghi.")

            elif mode == "all":
                symbols = get_target_symbols(target_db, symbol_arg="all")
                args.delay = 0.4
                args.interval = "1D"
                args.period = "quarter"
                args.report_type = "all"
                args.pages = 5
                args.force = False

                for cat_k, runner in CATEGORIES_REGISTRY.items():
                    if not self.is_running:
                        break
                    print(f"\n--- BẮT ĐẦU PHÂN HỆ: {cat_k.upper()} ---")
                    try:
                        self._precheck_and_log(cat_k, symbols, target_db, force=False)
                        c = runner(symbols, writer, args)
                        print(f"  -> Hoàn tất {cat_k}: +{c:,} bản ghi.")
                    except Exception as ex_cat:
                        print(f"  -> [Lỗi] {cat_k}: {ex_cat}")
                writer.sync_buffer_to_target()

        except Exception as e:
            print(f"\n[!] LỖI TRONG TIẾN TRÌNH: {e}")

        duration = time.time() - start_time
        print("\n" + "═" * 80)
        print(f"KẾT THÚC TIẾN TRÌNH TRONG {duration:.2f} GIÂY")
        print("═" * 80 + "\n")

        self.after(0, self._finish_crawl)

    def _finish_crawl(self):
        self.is_running = False
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self.btn_refresh.configure(state="normal")
        self.refresh_status_async()


def main():
    app = VestaCrawlerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
