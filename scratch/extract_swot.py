import os
import re
import json

progress_dir = "d:/VESTA/Progress Report"
files = sorted([f for f in os.listdir(progress_dir) if f.endswith(".md")])

extracted_sections = {}

for fname in files:
    fpath = os.path.join(progress_dir, fname)
    with open(fpath, "r", encoding="utf-8") as f:
        content = f.read()
        
    lines = content.splitlines()
    
    findings = []
    current_heading = ""
    current_block = []
    recording = False
    
    target_keywords = ["ưu điểm", "nhược điểm", "điểm yếu", "hạn chế", "weakness", "strength", "swot", "đề xuất", "khoảng trống", "rủi ro"]
    
    for i, line in enumerate(lines):
        if line.startswith("#"):
            if recording and current_block:
                findings.append({
                    "heading": current_heading,
                    "text": "\n".join(current_block[:40]) # limit lines
                })
                current_block = []
                recording = False
            current_heading = line
            if any(k in line.lower() for k in target_keywords):
                recording = True
        elif recording:
            current_block.append(line)
            
    if recording and current_block:
        findings.append({
            "heading": current_heading,
            "text": "\n".join(current_block[:40])
        })
        
    extracted_sections[fname] = findings

with open("scratch/extracted_strengths_weaknesses.json", "w", encoding="utf-8") as f:
    json.dump(extracted_sections, f, ensure_ascii=False, indent=2)

print(f"Processed {len(files)} files.")
for fname, findings in extracted_sections.items():
    print(f"\n=== {fname} ({len(findings)} target sections) ===")
    for find in findings[:5]:
        print(f"  * {find['heading']}")
