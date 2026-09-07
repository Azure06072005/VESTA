import yaml

with open('configs/robots_global.yaml', 'r', encoding='utf-8') as f:
    cfg = yaml.safe_load(f)

t3 = cfg.get('tier3_sources', {})
for g, srcs in t3.items():
    print(f"=== GROUP: {g} ===")
    for k, v in srcs.items():
        st = str(v.get('status'))
        cnt = v.get('ingested_records_count', 0)
        url = v.get('base_url', '')
        print(f"  {k:20s} | status={st:8s} | count={cnt:7d} | url={url}")
