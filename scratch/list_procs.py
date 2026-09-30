import psutil

for p in psutil.process_iter(['pid', 'name', 'cmdline']):
    try:
        cmd = " ".join(p.info['cmdline'] or [])
        if "python" in p.info['name'].lower() or "vesta" in cmd.lower():
            print(f"PID {p.info['pid']}: {p.info['name']} | CMD: {cmd[:120]}")
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
