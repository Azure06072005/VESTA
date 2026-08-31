import os
import json
import re

def deep_dive(directory):
    # Endpoints we want to sample
    targets = {
        "NewsDetail": r"cafef.vn/du-lieu/[a-z0-9-]+-\d+\.chn",
        "ReportSummary": r"apiweb.cafef.vn/api/v1/BCTC/GetReportSummary",
        "FinancialIndicators": r"apiweb.cafef.vn/api/v2/BCTC/FinancialIndicators",
        "CoCauSoHuu": r"cafef.vn/du-lieu/Ajax/PageNew/CoCauSoHuu.ashx",
        "GDCoDong": r"cafef.vn/du-lieu/Ajax/PageNew/DataHistory/GDCoDong.ashx",
        "ListCeo": r"cafef.vn/du-lieu/Ajax/PageNew/ListCeo.ashx"
    }
    
    samples = {key: [] for key in targets}

    for filename in os.listdir(directory):
        if not filename.endswith('.har') or not filename.startswith('cafef_'):
            continue
            
        filepath = os.path.join(directory, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                har_data = json.load(f)
        except Exception:
            continue
            
        entries = har_data.get('log', {}).get('entries', [])
        for entry in entries:
            url = entry.get('request', {}).get('url', '')
            res_content = entry.get('response', {}).get('content', {}).get('text', '')
            
            if not res_content: continue
            
            for key, pattern in targets.items():
                if len(samples[key]) < 1 and re.search(pattern, url):
                    samples[key].append({
                        "url": url,
                        "text": res_content[:2000] # Take first 2000 chars to avoid massive logs
                    })
                    break

    with open('d:/VESTA/scratch/har_samples.txt', 'w', encoding='utf-8') as f:
        for key, data in samples.items():
            f.write(f"\n{'='*50}\nSAMPLE FOR: {key}\n{'='*50}\n")
            for item in data:
                f.write(f"URL: {item['url']}\n")
                f.write(f"Payload (truncated):\n{item['text']}\n\n")

if __name__ == '__main__':
    deep_dive('d:/VESTA/scratch')
