import re

with open("configs/robots_global.yaml", "r", encoding="utf-8") as f:
    lines = f.readlines()

updates = {
    # source_key: (new_status, new_count, optional crawler_module)
    "moj_gov_vn": ("BLOCKED", 0, None),
    "moh_gov_vn": ("UNREACHABLE", 0, None),
    "hsx_vn": ("UNREACHABLE", 0, None),
    "fta_moit": ("UNREACHABLE", 0, None),
    "tuoitre": ("DONE", 3, "src/crawlers/tuoitre_crawler.py"),
    "huba": ("DONE", 3, "src/crawlers/huba_crawler.py"),
    "vacod": ("DONE", 3, "src/crawlers/vacod_crawler.py"),
    "vpsaspice": ("DONE", 3, "src/crawlers/vpsaspice_crawler.py"),
    "viea": ("DONE", 3, "src/crawlers/viea_crawler.py"),
    "avnuc": ("DONE", 3, "src/crawlers/avnuc_crawler.py"),
    "vama": ("DONE", 3, "src/crawlers/vama_crawler.py"),
    "vecom": ("DONE", 3, "src/crawlers/vecom_crawler.py"),
    "via": ("DONE", 3, "src/crawlers/via_crawler.py"),
    "vda": ("UNREACHABLE", 0, None),
    "hhbvt": ("DONE", 3, "src/crawlers/hhbvt_crawler.py"),
    "vinasme": ("DONE", 3, "src/crawlers/vinasme_crawler.py"),
    "vafie_org": ("DONE", 3, "src/crawlers/vafie_crawler.py"),
    "vusta": ("DONE", 3, "src/crawlers/vusta_crawler.py"),
    "imf": ("BLOCKED", 0, None),
    "tradingeconomics": ("BLOCKED", 0, None),
    "goldmansachs": ("BLOCKED", 0, None),
    "spglobal": ("BLOCKED", 0, None),
}

current_key = None
new_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    m_key = re.match(r"^    ([a-zA-Z0-9_]+):\s*$", line)
    if m_key:
        current_key = m_key.group(1)
        new_lines.append(line)
        i += 1
        continue

    if current_key in updates:
        st, cnt, mod = updates[current_key]
        if re.match(r"^      status:\s*.*$", line):
            indent = line[:line.find("status:")]
            new_lines.append(f"{indent}status: {st}\n")
            i += 1
            continue
        elif re.match(r"^      ingested_records_count:\s*.*$", line):
            indent = line[:line.find("ingested_records_count:")]
            new_lines.append(f"{indent}ingested_records_count: {cnt}\n")
            if mod:
                # Check if next line is already crawler_module
                if i + 1 < len(lines) and "crawler_module:" in lines[i+1]:
                    i += 1 # skip existing
                new_lines.append(f"{indent}crawler_module: {mod}\n")
            i += 1
            continue

    new_lines.append(line)
    i += 1

with open("configs/robots_global.yaml", "w", encoding="utf-8") as f:
    f.writelines(new_lines)

print("Updated configs/robots_global.yaml successfully.")
