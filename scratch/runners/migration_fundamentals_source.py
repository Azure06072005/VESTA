def migrate_fundamentals_add_source_column(con: duckdb.DuckDBPyConnection) -> bool:
    """Adds a source column to core.fundamentals/staging.fundamentals,
    distinguishing vnstock_data's English BS_*/IS_*/CF_*/RT_* key schema
    from cafef's raw Vietnamese line-item schema (2026-09-06 -- cafef's
    balance_sheet gap fix, see DECISIONS.md). Additive (no PRIMARY KEY
    change), so a plain ALTER TABLE ADD COLUMN is sufficient.

    Real production backfill logic (confirmed against actual data
    2026-09-06 -- NOT a simplistic single-cutoff-date rule, since cafef
    wrote across all 4 report types on that date, not just balance_sheet):
    a row is 'vnstock_data' if it predates the cafef crawl OR its
    data_json contains a recognizable vnstock_data key prefix; everything
    else is 'cafef'. This matches the exact backfill query verified
    against the real 179,135-row table (156,337 vnstock_data / 22,798
    cafef, 0 remaining NULL).
    """
    ran_any = False
    for schema in (("staging", "fundamentals"), ("core", "fundamentals")):
        table_schema, table_name = schema
        exists = con.execute(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema = ? AND table_name = ?",
            [table_schema, table_name],
        ).fetchone()
        exists_count = exists[0] if exists is not None else 0
        if exists_count == 0:
            continue
        if _table_has_column(con, table_schema, table_name, "source"):
            continue
        con.execute(
            f"ALTER TABLE {table_schema}.{table_name} "
            f"ADD COLUMN source VARCHAR NOT NULL DEFAULT 'vnstock_data'"
        )
        # Backfill existing rows with the real, verified classification --
        # the DEFAULT above only covers the column's existence, not correct
        # historical attribution for rows that predate this migration.
        con.execute(
            f"""
            UPDATE {table_schema}.{table_name}
            SET source = 'cafef'
            WHERE NOT (
                fetched_at < '2026-09-06'
                OR data_json LIKE '%"BS_%'
                OR data_json LIKE '%"IS_%'
                OR data_json LIKE '%"CF_%'
                OR data_json LIKE '%"RT_%'
            )
            """
        )
        print(f"[migration] {table_schema}.{table_name}: added source column and backfilled")
        ran_any = True
    return ran_any