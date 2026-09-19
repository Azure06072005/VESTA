import os
import sys
import json
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')

# Set API key
os.environ["VNSTOCK_API_KEY"] = "vnstock_f84ed9f3014e77c53a88e3eae1bc1be8"

print("Python executable:", sys.executable)

try:
    import vnstock
    print("vnstock version:", getattr(vnstock, "__version__", "unknown"))
except Exception as e:
    print("Error importing vnstock:", e)

try:
    from vnstock_data import Market, Fundamental, Reference, show_api, show_doc
    print("vnstock_data imported successfully!")
    print("\n=== AVAILABLE APIS (show_api) ===")
    show_api()
except Exception as e:
    print("Error importing vnstock_data:", e)

try:
    import vnstock_news
    print("\nvnstock_news imported successfully!")
except Exception as e:
    print("Error importing vnstock_news:", e)

try:
    import vnstock_ta
    print("\nvnstock_ta imported successfully!")
except Exception as e:
    print("Error importing vnstock_ta:", e)
