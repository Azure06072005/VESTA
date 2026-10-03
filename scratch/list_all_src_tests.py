import os
import glob
import sys

sys.stdout.reconfigure(encoding='utf-8')

print("=== SRC FILES ===")
for root, dirs, files in os.walk('src'):
    for f in files:
        if f.endswith('.py'):
            rel = os.path.relpath(os.path.join(root, f)).replace('\\', '/')
            print(rel)

print("\n=== TEST FILES ===")
for root, dirs, files in os.walk('tests'):
    for f in files:
        if f.endswith('.py') and f.startswith('test_'):
            rel = os.path.relpath(os.path.join(root, f)).replace('\\', '/')
            print(rel)
