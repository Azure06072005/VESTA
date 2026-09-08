import duckdb
from urllib.parse import urlparse
import sys

sys.stdout.reconfigure(encoding='utf-8')
con = duckdb.connect('d:/VESTA/db/vesta_latest_backup.duckdb', read_only=True)

print("=== 1. TIN TỨC DOANH NGHIỆP & CỔ PHIẾU (core.news) ===")
res_news = con.execute('''
    SELECT 
        source, 
        count(*) as cnt, 
        min(published_at) as min_dt, 
        max(published_at) as max_dt
    FROM core.news 
    GROUP BY source 
    ORDER BY cnt DESC
''').fetchall()

for s, cnt, min_d, max_d in res_news:
    sample_url = con.execute('SELECT source_url FROM core.news WHERE source = ? AND source_url IS NOT NULL LIMIT 1', [s]).fetchone()
    url = sample_url[0] if sample_url else ''
    domain = urlparse(url).netloc or s
    print(f"  * Nguồn: {s:<12} | Website: {domain:<25} | Số bài: {cnt:7,d} | Thời gian: {str(min_d)[:10]} -> {str(max_d)[:10]}")

print("\n=== 2. CHÍNH SÁCH VĨ MÔ & BÁO CHÍ KINH TẾ (core.macro_policy) ===")
res_macro = con.execute('''
    SELECT 
        source, 
        issuing_body,
        count(*) as cnt, 
        min(published_at) as min_dt, 
        max(published_at) as max_dt
    FROM core.macro_policy 
    GROUP BY source, issuing_body
    ORDER BY cnt DESC
''').fetchall()

source_agg = {}
for s, body, cnt, min_d, max_d in res_macro:
    if s not in source_agg:
        sample_url = con.execute('SELECT source_url FROM core.macro_policy WHERE source = ? AND source_url IS NOT NULL LIMIT 1', [s]).fetchone()
        url = sample_url[0] if sample_url else ''
        domain = urlparse(url).netloc or s
        source_agg[s] = {'body': body or s, 'cnt': 0, 'domain': domain, 'min_d': min_d, 'max_d': max_d}
    source_agg[s]['cnt'] += cnt

print(f"Tổng số nguồn vĩ mô/báo chí đã cào: {len(source_agg)} website/cơ quan\n")
for s, data in sorted(source_agg.items(), key=lambda x: -x[1]['cnt']):
    body_txt = data['body'][:32] if data['body'] else s
    d_name = data['domain']
    print(f"  * {s:<20} | {d_name:<28} | {body_txt:<32} | {data['cnt']:6,d} bài | {str(data['min_d'])[:10]} -> {str(data['max_d'])[:10]}")

print("\n=== 3. BÁO CÁO PHÂN TÍCH DOANH NGHIỆP TỪ CÔNG TY CHỨNG KHOÁN (core.stock_research_reports) ===")
cnt_reports = con.execute("SELECT count(*) FROM core.stock_research_reports").fetchone()[0]
sample_rep = con.execute("SELECT broker, min(report_date), max(report_date) FROM core.stock_research_reports GROUP BY broker LIMIT 1").fetchone()
print(f"  * Nguồn: vietstock.vn | Công ty phân tích: {sample_rep[0] if sample_rep else 'Đa CTCK'} | Số báo cáo: {cnt_reports:,}")

total_all = sum(r[1] for r in res_news) + sum(d['cnt'] for d in source_agg.values()) + cnt_reports
print(f"\n=========================================================================")
print(f">>> TỔNG CỘNG TẤT CẢ CÁC BÀI BÁO & BÁO CÁO ĐÃ CÀO: {total_all:,} bài viết/tài liệu <<<")
print(f"=========================================================================")

con.close()
