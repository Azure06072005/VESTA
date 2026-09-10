import duckdb
import yaml
import sys

sys.stdout.reconfigure(encoding='utf-8')

con = duckdb.connect('d:/VESTA/db/vesta_latest_backup.duckdb', read_only=True)
crawled_macro = set(r[0] for r in con.execute('SELECT DISTINCT source FROM core.macro_policy').fetchall())
crawled_news = set(r[0] for r in con.execute('SELECT DISTINCT source FROM core.news').fetchall())
all_db_sources = crawled_macro | crawled_news
con.close()

with open('configs/robots_global.yaml', 'r', encoding='utf-8') as f:
    cfg = yaml.safe_load(f)

# Explicit source mapping from YAML keys to DB source names where naming differs
KEY_MAP = {
    'sbv_gov_vn': 'sbv',
    'baochinhphu_vn': 'baochinhphu',
    'moit_gov_vn': 'moit',
    'ssc_gov_vn': 'ssc',
    'cafef_vn': 'cafef',
    'vietstock_vn': 'vietstock',
    'vneconomy_vn': 'vneconomy',
    'tinnhanhchungkhoan_vn': 'tinnhanhchungkhoan',
    'baodautu_vn': 'baodautu',
    'thoibaonganhang_vn': 'thoibaonganhang',
    'vasep_com_vn': 'vasep',
    'vnba_org_vn': 'vnba',
    'vsa_com_vn': 'vsa',
    'vita_vn': 'vita',
    'vafie_org': 'vafie',
    'luatvn': 'luatvietnam',
    'fta_moit': 'moit',
    'data_worldbank_org': 'worldbank',
}

truly_uncrawled = []
for g, srcs in cfg.get('tier3_sources', {}).items():
    for k, v in srcs.items():
        db_key = KEY_MAP.get(k, k)
        if db_key not in all_db_sources:
            truly_uncrawled.append({
                'group': g,
                'key': k,
                'name': v.get('name', k),
                'base_url': v.get('base_url') or v.get('url') or '',
                'sitemap_url': v.get('sitemap_url') or ''
            })

print(f'Total TRULY uncrawled sites across Tier 3: {len(truly_uncrawled)}')
for item in truly_uncrawled:
    target_url = item['sitemap_url'] or item['base_url']
    print(f"  [{item['group']:<25}] {item['key']:<20} | {target_url}")
