import duckdb
import sys

sys.stdout.reconfigure(encoding='utf-8')
con = duckdb.connect('db/vesta_snapshot.duckdb', read_only=True)
res = con.execute('''
    SELECT symbol, 
           count(*) as total_events,
           count(payout_delay_days) as dividend_payout_events,
           round(avg(payout_delay_days), 1) as avg_payout_delay,
           min(payout_delay_days) as min_delay,
           max(payout_delay_days) as max_delay
    FROM core.corporate_events
    WHERE symbol IN ('ACB', 'BCM', 'BID', 'BVH', 'CTG', 'FPT', 'GAS', 'GVR', 'HDB', 'HPG', 'MBB', 'MSN', 'MWG', 'PLX', 'POW', 'SAB', 'SHB', 'SSB', 'SSI', 'STB', 'TCB', 'TPB', 'VCB', 'VHM', 'VIB', 'VIC', 'VJC', 'VNM', 'VPB', 'VRE')
    GROUP BY symbol
    ORDER BY avg_payout_delay DESC NULLS LAST
''').fetchall()

print('=== THONG KE DO TRE CHI TRA CO TUC (PAYOUT DELAY DAYS) TREN RO VN30 ===')
print(f'{"Symbol":<6} | {"Total":<8} | {"Payout Count":<15} | {"Avg Delay (days)":<18} | {"Min":<6} | {"Max":<6}')
print('-' * 70)
for r in res:
    avg_d = f'{r[3]} days' if r[3] is not None else 'N/A'
    min_d = str(r[4]) if r[4] is not None else '-'
    max_d = str(r[5]) if r[5] is not None else '-'
    print(f'{r[0]:<6} | {r[1]:<8} | {r[2]:<15} | {avg_d:<18} | {min_d:<6} | {max_d:<6}')

con.close()
