with open('web/src/pages/DashboardPage.tsx', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if 'selectedSymbol' in line:
        print(f"Line {i+1}: {line.strip()[:100]}")
