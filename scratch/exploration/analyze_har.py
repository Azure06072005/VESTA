import os
import json
import re
from urllib.parse import urlparse

def analyze_hars(directory):
    endpoints = {}
    
    for filename in os.listdir(directory):
        if not filename.endswith('.har') or not filename.startswith('cafef_'):
            continue
            
        filepath = os.path.join(directory, filename)
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                har_data = json.load(f)
        except Exception as e:
            continue
            
        entries = har_data.get('log', {}).get('entries', [])
        
        for entry in entries:
            req = entry.get('request', {})
            res = entry.get('response', {})
            
            url = req.get('url', '')
            method = req.get('method', '')
            status = res.get('status', 0)
            
            if not url or method == 'OPTIONS': continue
            
            parsed = urlparse(url)
            
            if 'cafef' not in parsed.netloc and 'cafef' not in parsed.path:
                continue
                
            ext = os.path.splitext(parsed.path)[1].lower()
            if ext in ['.png', '.jpg', '.jpeg', '.gif', '.css', '.js', '.woff', '.woff2', '.ttf', '.svg', '.ico']:
                continue
                
            if 'google-analytics' in url or 'ads' in url or 'pixel' in url or 'tracking' in url:
                continue

            path = parsed.path
            
            # Generalized endpoint matching
            clean_path = re.sub(r'/[A-Z0-9]{3}-\d+/', '/{SYMBOL}-ID/', path)
            clean_path = re.sub(r'/[a-z0-9-]+-\d+\.chn', '/{ARTICLE-SLUG}.chn', clean_path)
            clean_path = re.sub(r'/[A-Z0-9]{3}/', '/{SYMBOL}/', clean_path)
            clean_path = re.sub(r'\d{5,}', '{ID}', clean_path)
            
            key = f"{method} {parsed.netloc}{clean_path}"
            
            if key not in endpoints:
                endpoints[key] = {
                    'examples': set(),
                    'params': set(),
                    'content_types': set(),
                    'count': 0
                }
                
            endpoints[key]['count'] += 1
            if len(endpoints[key]['examples']) < 3:
                endpoints[key]['examples'].add(url)
                
            for param in req.get('queryString', []):
                endpoints[key]['params'].add(param.get('name'))
                
            content_type = res.get('content', {}).get('mimeType', 'unknown')
            if content_type:
                endpoints[key]['content_types'].add(content_type.split(';')[0])

    with open('d:/VESTA/scratch/har_analysis_utf8.txt', 'w', encoding='utf-8') as f:
        f.write("--- INTERESTING ENDPOINTS FOUND ---\n")
        sorted_endpoints = sorted(endpoints.items(), key=lambda x: x[1]['count'], reverse=True)
        
        for key, data in sorted_endpoints:
            if not any(ct in ['application/json', 'text/html', 'text/plain'] for ct in data['content_types']):
                if data['count'] < 3:
                    continue
                    
            f.write(f"\nEndpoint: {key} (Called {data['count']} times)\n")
            f.write(f"Content-Types: {', '.join(data['content_types'])}\n")
            f.write(f"Params: {', '.join(data['params'])}\n")
            f.write("Examples:\n")
            for ex in list(data['examples'])[:2]:
                f.write(f"  - {ex}\n")

if __name__ == '__main__':
    analyze_hars('d:/VESTA/scratch')
