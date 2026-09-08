import duckdb

conn = duckdb.connect('d:/VESTA/db/vesta_latest_backup.duckdb', read_only=True)
print('--- core.macro_policy columns ---')
print(conn.execute("PRAGMA table_info('core.macro_policy')").df()[['cid', 'name', 'type', 'notnull', 'dflt_value', 'pk']])

print('\n--- core.news columns ---')
print(conn.execute("PRAGMA table_info('core.news')").df()[['cid', 'name', 'type', 'notnull', 'dflt_value', 'pk']])

print('\n--- staging.macro_policy exists? ---')
try:
    print(conn.execute("PRAGMA table_info('staging.macro_policy')").df()[['cid', 'name', 'type']])
except Exception as e:
    print("staging.macro_policy not found or error:", e)

conn.close()
