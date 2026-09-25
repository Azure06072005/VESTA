import json
import sys

sys.stdout.reconfigure(encoding='utf-8')
data = json.load(open('d:/VESTA/scratch/all_reports_pros_cons.json', encoding='utf-8'))

for fname, sections in data.items():
    print(f"\n{'='*30} {fname} {'='*30}")
    for sec in sections:
        header = sec['header']
        content = sec['content']
        # If it contains weakness or limitation
        if any(w in header.lower() for w in ['nhược điểm', 'điểm yếu', 'hạn chế', 'swot', 'đề xuất', 'cons', 'weakness']):
            lines = content.split('\n')
            print(f"\n--- {header} ---")
            for l in lines[1:15]:  # print first few lines of content
                if l.strip():
                    print(f"  {l.strip()}")
