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

    def free_port(port: int, host: str = "127.0.0.1"):
        import socket
        import subprocess
        import time
        for attempt in range(5):
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                s.bind((host, port))
                s.close()
                return
            except OSError:
                pass
            print(f"⚠️ Cổng {port} đang bị chiếm dụng (lần thử {attempt+1}/5). Đang tự động giải phóng...")
            try:
                out = subprocess.check_output(
                    f'powershell -Command "Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess"',
                    shell=True,
                    text=True,
                )
                pids = set(out.strip().split())
                for p in pids:
                    if p and p.isdigit():
                        pid_int = int(p)
                        if pid_int > 4 and pid_int != os.getpid():
                            subprocess.run(f"taskkill /F /PID {pid_int}", shell=True, capture_output=True)
                            print(f"✓ Đã buộc dừng tiến trình chiếm dụng PID {pid_int}.")
                time.sleep(1)
            except Exception as e:
                print(f"Cảnh báo khi giải phóng cổng: {e}")
                time.sleep(1)

    free_port(args.port, args.host)

    if args.open:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    import uvicorn
    uvicorn.run("src.service.console_api:app", host=args.host, port=args.port, reload=False)



if __name__ == "__main__":
    main()
