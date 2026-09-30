import duckdb

try:
    con = duckdb.connect('db/vesta_backup.duckdb', read_only=False)
    print("vesta_backup.duckdb open read-write OK!")
    con.close()
except Exception as e:
    print("Error opening vesta_backup:", e)
