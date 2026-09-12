import os
import glob
import re

robots_dir = 'scratch/exploration/robots'
files = glob.glob(f'{robots_dir}/*.txt')
print(f"Total robots files in {robots_dir}: {len(files)}")

report_rows = []
for f in sorted(files):
    name = os.path.basename(f)
    with open(f, 'r', encoding='utf-8', errors='ignore') as fp:
        raw_text = fp.read()
        lines = [line.strip() for line in raw_text.splitlines() if line.strip() and not line.strip().startswith('#')]
    
    crawl_delays = [l for l in lines if 'crawl-delay' in l.lower()]
    disallows = [l for l in lines if l.lower().startswith('disallow:')]
    allows = [l for l in lines if l.lower().startswith('allow:')]
    user_agents = [l for l in lines if l.lower().startswith('user-agent:')]
    
    # Determine verdict / status
    verdict = "ALLOW_ALL"
    if any(l.strip() == "Disallow: /" for l in disallows):
        # check if it applies to User-agent: *
        verdict = "DISALLOW_ALL"
    elif disallows:
        verdict = f"RESTRICTED ({len(disallows)} paths)"
    elif allows and not disallows:
        verdict = "ALLOW_ALL"
    
    # Check if html or php error
    if "<html" in raw_text.lower() or "parse error" in raw_text.lower() or "404" in raw_text:
        verdict = "HTML_OR_ERROR"
        
    delay_str = crawl_delays[0] if crawl_delays else "None"

    report_rows.append({
        "file": name,
        "lines": len(lines),
        "delay": delay_str,
        "verdict": verdict,
        "total_disallow": len(disallows),
        "total_allow": len(allows),
        "sample_disallows": disallows[:2]
    })

print(f"{'Filename':<35} | {'Lines':<5} | {'Crawl-Delay':<18} | {'Disallows':<9} | {'Verdict'}")
print("-" * 95)
for r in report_rows:
    print(f"{r['file']:<35} | {r['lines']:<5} | {r['delay']:<18} | {r['total_disallow']:<9} | {r['verdict']}")
