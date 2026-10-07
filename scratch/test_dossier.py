import duckdb
import json

def get_full_stock_dossier(symbol):
    sym = symbol.strip().upper()
    dossier = {
        'symbol': sym,
        'overview': {},
        'shareholders': [],
        'fundamentals': {},
        'ohlcv_history': [],
        'foreign_flow': {},
        'events': [],
        'news': []
    }
    
    # 1. Snapshot DB
    with duckdb.connect('db/vesta_snapshot.duckdb', read_only=True) as con:
        # Overview
        row = con.execute('''
            SELECT symbol, exchange, charter_capital, ceo_name, company_type, free_float_percentage, outstanding_shares 
            FROM core.company_overview WHERE symbol = ?
        ''', [sym]).fetchone()
        if row:
            dossier['overview'] = {
                'symbol': row[0], 'exchange': row[1], 'charter_capital': row[2],
                'ceo_name': row[3], 'company_type': row[4],
                'free_float_pct': row[5], 'outstanding_shares': row[6]
            }
        # Shareholders
        shs = con.execute('''
            SELECT shareholder_name, ownership_percentage 
            FROM core.company_shareholders 
            WHERE symbol = ? ORDER BY ownership_percentage DESC LIMIT 5
        ''', [sym]).fetchall()
        dossier['shareholders'] = [{'name': s[0], 'ownership_pct': s[1]} for s in shs]
        
        # Fundamentals
        f_row = con.execute('''
            SELECT data_json FROM core.fundamentals 
            WHERE symbol = ? AND report_type = 'ratio' 
            ORDER BY period_end DESC LIMIT 1
        ''', [sym]).fetchone()
        if f_row and f_row[0]:
            try:
                dj = json.loads(f_row[0])
                dossier['fundamentals'] = {
                    'pe': dj.get('RT_VALUE_PE'),
                    'pb': dj.get('RT_VALUE_PB'),
                    'roe': dj.get('RT_VALUE_ROE'),
                    'debt_equity': dj.get('RT_VALUE_DEBT_EQUITY'),
                    'net_margin': dj.get('RT_VALUE_NET_MARGIN')
                }
            except Exception:
                pass
                
        # Foreign flow
        ff = con.execute('''
            SELECT net_value, date FROM core.market_foreign_flow_daily 
            WHERE symbol = ? ORDER BY date DESC LIMIT 1
        ''', [sym]).fetchone()
        if ff and ff[0] is not None:
            dossier['foreign_flow'] = {'net_value': float(ff[0]), 'date': str(ff[1])}
            
        # Events
        evs = con.execute('''
            SELECT event_type, event_date, detail_json FROM core.corporate_events 
            WHERE symbol = ? ORDER BY event_date DESC LIMIT 3
        ''', [sym]).fetchall()
        for ev in evs:
            title = ev[0] or "Sự kiện"
            if ev[2]:
                try:
                    dj = json.loads(ev[2])
                    title = dj.get('event_title_vi') or dj.get('event_name_vi') or title
                except Exception:
                    pass
            dossier['events'].append({'type': ev[0], 'date': str(ev[1]), 'title': title})

    # 2. OHLCV DB
    with duckdb.connect('db/vesta_ohlcv.duckdb', read_only=True) as con:
        bars = con.execute('''
            SELECT date, open, high, low, close, volume 
            FROM core.market_ohlcv_daily 
            WHERE symbol = ? ORDER BY date DESC LIMIT 10
        ''', [sym]).fetchall()
        dossier['ohlcv_history'] = [
            {'date': str(b[0]), 'open': float(b[1]), 'high': float(b[2]), 'low': float(b[3]), 'close': float(b[4]), 'volume': float(b[5])} 
            for b in bars
        ]

    # 3. News DB
    with duckdb.connect('db/vesta_news.duckdb', read_only=True) as con:
        nws = con.execute('''
            SELECT headline, source, published_at FROM core.news 
            WHERE symbol = ? OR headline ILIKE ? 
            ORDER BY published_at DESC LIMIT 5
        ''', [sym, f'%{sym}%']).fetchall()
        dossier['news'] = [{'headline': n[0], 'source': n[1], 'published_at': str(n[2])} for n in nws]

    return dossier

for s in ['NVL', 'PNJ']:
    d = get_full_stock_dossier(s)
    print('=== DOSSIER FOR', s, '===')
    print('Overview:', d['overview'])
    print('Shareholders count:', len(d['shareholders']))
    for sh in d['shareholders']:
        print('  Shareholder:', sh['name'], f"({sh['ownership_pct']}%)")
    print('Fundamentals:', d['fundamentals'])
    print('Recent 5 prices:', [(b['date'], b['close'], b['volume']) for b in d['ohlcv_history'][:5]])
    print('Recent 3 news:')
    for n in d['news'][:3]:
        print('  News:', n['headline'], 'from', n['source'], 'at', n['published_at'])
