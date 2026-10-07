"""run_console.py

One-click Launcher for VESTA Web Console.
Starts the Unified FastAPI Gateway & Static Web Server at http://localhost:8899.
"""

import argparse
import os
import pathlib
import sys
import webbrowser

REPO_ROOT = pathlib.Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Khởi động VESTA Unified Web Console")
    parser.add_argument("--port", type=int, default=8899, help="Cổng chạy dịch vụ (mặc định: 8899)")
    parser.add_argument("--host", default="127.0.0.1", help="Host bind (mặc định: 127.0.0.1)")
    parser.add_argument("--open", action="store_true", default=True, help="Tự động mở trình duyệt web")
    parser.add_argument("--no-open", dest="open", action="store_false", help="Không tự động mở trình duyệt")
    parser.add_argument("--no-crawl", dest="auto_crawl", action="store_false", default=True, help="Tắt tự động cào dữ liệu mới nhất khi khởi động")
    args = parser.parse_args()

    if args.auto_crawl:
        os.environ["VESTA_AUTO_CRAWL_ON_STARTUP"] = "1"
    else:
        os.environ["VESTA_AUTO_CRAWL_ON_STARTUP"] = "0"

    url = f"http://{args.host}:{args.port}"

    print("═" * 70)
    print("VESTA QUANT LABS — UNIFIED WEB CONSOLE (SLM × LAM v2.0)")
    print("Powered by FastAPI + DuckDB Lakehouse + React TypeScript")
    print(f"Địa chỉ Web Console: {url}")
    print(f"Tự động cào dữ liệu mới nhất: {'BẬT (Chạy ngầm)' if args.auto_crawl else 'TẮT'}")
    print("Các phân hệ tích hợp:")
    print("    • 1. Overview & Architecture (Kế thừa phong cách kietfolio)")
    print("    • 2. Market Dashboard (CafeF & Vietstock, Heatmap, Nến TradingView)")
    print("    • 3. Crawler Pipeline Controller (Thay thế GUI cũ, SSE Live Stream)")
    print("    • 4. Preprocessing & QA Audit (F101-F106 PIT, Ma trận F203)")
    print("    • 5. Model Feedback & Inference (PhoBERT + Kolmogorov + Qwen SLM)")
    print("    • 6. Bot Arena Studio (308 Bots, Vốn 10M VNĐ Odd-lot, AI Generator)")
    print("═" * 70)

    if args.open:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    import uvicorn
    uvicorn.run("src.service.console_api:app", host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
