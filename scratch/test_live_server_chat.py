import urllib.request
import json

url = "http://127.0.0.1:8899/api/bot-arena/chat"
payload = {
    "message": "Tôi muốn đầu tư NVL và PNJ vốn 10 triệu VNĐ, hãy tư vấn chiến lược tốt nhất.",
    "initial_cash": 10000000.0,
    "risk_tolerance": "medium"
}
data = json.dumps(payload).encode("utf-8")
req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})

with urllib.request.urlopen(req, timeout=15) as res:
    out = json.loads(res.read().decode("utf-8"))
    print("Status:", res.status)
    print("Keys:", list(out.keys()))
    print("Target assets:", out.get("target_assets"))
    print("Focus title:", out.get("focus_title"))
    print("Custom ranked bots count:", len(out.get("custom_ranked_bots", [])))
    for b in out.get("custom_ranked_bots", [])[:3]:
        print(f"  #{b['rank']} {b['bot_id']} | {b['strategy_id']} | Sharpe: {b['mean_sharpe']}")
        print(f"     Action: {b.get('tailored_action')}")
    print("\nModel used:", out.get("model_used"))
    print("\nReply excerpt:\n", out.get("reply")[:500])
