import duckdb
import pandas as pd
import json

con = duckdb.connect('d:/VESTA/db/vesta_snapshot.duckdb', read_only=True)

# 1. Get all tables in all schemas
tables_df = con.execute("""
    SELECT table_schema, table_name, table_type 
    FROM information_schema.tables 
    ORDER BY table_schema, table_name
""").df()

print(f"Total tables/views: {len(tables_df)}")
results = []

for idx, row in tables_df.iterrows():
    schema = row['table_schema']
    table = row['table_name']
    t_type = row['table_type']
    
    # Get count
    try:
        cnt = con.execute(f'SELECT COUNT(*) FROM "{schema}"."{table}"').fetchone()[0]
    except Exception as e:
        cnt = f"ERROR: {e}"
        
    # Get columns
    cols_df = con.execute(f"""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_schema = '{schema}' AND table_name = '{table}'
        ORDER BY ordinal_position
    """).df()
    
    cols = cols_df['column_name'].tolist()
    
    # Check for symbol / ticker columns
    sym_cols = [c for c in cols if any(k in c.lower() for k in ['symbol', 'ticker', 'code', 'stock'])]
    # Check for date / time columns
    date_cols = [c for c in cols if any(k in c.lower() for k in ['date', 'time', 'year', 'quarter', 'session', 'crawl', 'created', 'publish'])]
    
    results.append({
        'schema': schema,
        'table': table,
        'type': t_type,
        'row_count': cnt,
        'num_cols': len(cols),
        'cols': cols,
        'sym_cols': sym_cols,
        'date_cols': date_cols
    })

with open("scratch/db_overview.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print("Saved overview to scratch/db_overview.json")
for r in results:
    print(f"[{r['schema']}.{r['table']}] ({r['type']}): {r['row_count']} rows | cols: {r['num_cols']} | sym: {r['sym_cols']} | date: {r['date_cols']}")

con.close()
