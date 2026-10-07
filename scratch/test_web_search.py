import urllib.request
import urllib.parse
import re

def search_web_snippets(query: str, max_results: int = 3):
    url = 'https://html.duckduckgo.com/html/?q=' + urllib.parse.quote(query)
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    results = []
    try:
        with urllib.request.urlopen(req, timeout=5) as res:
            html = res.read().decode('utf-8', errors='ignore')
            snippets = re.findall(r'<a class="result__snippet[^>]*>(.*?)</a>', html, re.DOTALL)
            for snip in snippets[:max_results]:
                clean = re.sub(r'<[^<]+?>', '', snip).strip()
                if clean:
                    results.append(clean)
    except Exception as e:
        print(f"Search error: {e}")
    return results

if __name__ == '__main__':
    res = search_web_snippets("co phieu NVL PNJ")
    print(f"Results count: {len(res)}")
    for r in res:
        print("-", r[:100])
