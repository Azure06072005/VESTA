import duckdb
import os

dbs = [
    ('vesta_news', 'db/vesta_news.duckdb'),
    ('vesta_market_index', 'db/vesta_market_index.duckdb'),
    ('vesta_fundamentals', 'db/vesta_fundamentals.duckdb'),
    ('vesta_events', 'db/vesta_events.duckdb'),
]

for db_name, db_path in dbs:
    print('=' * 80)
    print(f'DATABASE: {db_name} ({db_path})')
    print('=' * 80)
    if not os.path.exists(db_path):
        print(f'File {db_path} does not exist!')
        continue
    
    con = duckdb.connect(db_path, read_only=True)
    tables = con.execute("SELECT table_schema, table_name, table_type FROM information_schema.tables WHERE table_schema IN ('core', 'staging', 'preprocessed', 'meta') ORDER BY table_schema, table_name").fetchall()
    print(f'Found {len(tables)} tables/views:')
    for schema, t_name, t_type in tables:
        full_name = f'{schema}.{t_name}'
        count = con.execute(f'SELECT count(*) FROM {full_name}').fetchone()[0]
        cols = [c[0] for c in con.execute(f'DESCRIBE {full_name}').fetchall()]
        
        date_candidates = [c for c in cols if any(k in c.lower() for k in ['date', 'time', 'published', 'period', 'year'])]
        sym_candidates = [c for c in cols if any(k in c.lower() for k in ['symbol', 'ticker', 'code'])]
        
        date_col = date_candidates[0] if date_candidates else None
        sym_col = sym_candidates[0] if sym_candidates else None
        
        date_str = 'N/A'
        sym_str = 'N/A'
        
        if date_col:
            try:
                min_d, max_d = con.execute(f'SELECT min({date_col}), max({date_col}) FROM {full_name}').fetchone()
                date_str = f'{date_col}: {min_d} -> {max_d}'
            except Exception as e:
                date_str = f'{date_col} err: {e}'
        
        if sym_col:
            try:
                cnt_sym = con.execute(f'SELECT count(DISTINCT {sym_col}) FROM {full_name}').fetchone()[0]
                sym_str = f'{sym_col}: {cnt_sym} unique'
            except Exception as e:
                sym_str = f'{sym_col} err: {e}'
                
        print(f'  • [{schema:12}] {t_name:30} ({t_type:10}): {count:10} rows | {sym_str:25} | {date_str}')
    con.close()
