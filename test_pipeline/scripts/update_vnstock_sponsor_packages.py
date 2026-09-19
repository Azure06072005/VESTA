import os
import sys
import subprocess
sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, r"D:\vnstock\.venv\Lib\site-packages")
from vnstock_installer.api import VnstockAPIClient

api_key = "vnstock_f84ed9f3014e77c53a88e3eae1bc1be8"
client = VnstockAPIClient(api_key=api_key, python_executable=r"D:\vnstock\.venv\Scripts\python.exe")

print("1. Registering device...")
ok, msg, data = client.register_device()
print(f" -> Register result: ok={ok}, msg={msg}")
if data:
    print(f" -> Tier: {data.get('tier')}, User: {data.get('userName', data.get('user_name'))}")

print("\n2. Listing available packages...")
ok, pkg_info = client.list_available_packages()
print(f" -> Packages: {pkg_info}")

if ok and isinstance(pkg_info, dict) and 'packages' in pkg_info:
    for p in pkg_info['packages']:
        p_name = p['name']
        print(f"\n3. Downloading {p_name} (version {p.get('version')})...")
        d_ok, wheel_path = client.download_package(p_name)
        print(f" -> Download: ok={d_ok}, path={wheel_path}")
        if d_ok and wheel_path and os.path.exists(wheel_path):
            print(f" -> Installing {wheel_path} into d:\\vnstock\\.venv...")
            cmd = [r"D:\vnstock\.venv\Scripts\python.exe", "-m", "pip", "install", "--upgrade", "--no-deps", wheel_path]
            res = subprocess.run(cmd, capture_output=True, text=True)
            print(f" -> Install output: {res.stdout.strip()} {res.stderr.strip()}")
