import os
import re

pattern = re.compile(r'F\d{3}')
for root, dirs, files in os.walk('web/src'):
    for f in files:
        if f.endswith(('.tsx', '.ts')):
            p = os.path.join(root, f)
            with open(p, 'r', encoding='utf-8') as file:
                lines = file.readlines()
            matches = [(i+1, line.strip()) for i, line in enumerate(lines) if pattern.search(line)]
            if matches:
                print(f"=== {p} ({len(matches)} matches) ===")
                for lno, text in matches:
                    # filter out internal variable names like getF203RegimeMatrix if only in api.ts
                    print(f"  L{lno}: {text[:100]}")
