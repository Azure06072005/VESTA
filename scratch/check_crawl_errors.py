import sys
import duckdb

sys.stdout.reconfigure(encoding='utf-8')

for db_path in ['db/vesta_snapshot.duckdb', 'db/vesta_ohlcv.duckdb', 'db/vesta_news.duckdb']:
    print(f"\n=======================================================")
    print(f"=== KIỂM TRA LỖI CRAWL TRONG: {db_path} ===")
    print(f"=======================================================")
    try:
        con = duckdb.connect(db_path, read_only=True)
        # Kiểm tra bảng meta.crawl_progress
        has_table = con.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='meta' AND table_name='crawl_progress'").fetchone()[0]
        if has_table:
            total_records = con.execute("SELECT count(*) FROM meta.crawl_progress").fetchone()[0]
            print(f"Tổng số bản ghi trong meta.crawl_progress: {total_records:,}")
            errs = con.execute("""
                SELECT dataset_name, status, count(*) 
                FROM meta.crawl_progress 
                WHERE status != 'success' 
                GROUP BY dataset_name, status
                ORDER BY count(*) DESC
            """).fetchall()
            if not errs:
                print("  -> Tuyệt vời: 100% bản ghi đều ở trạng thái 'success' (0 lỗi).")
            else:
                print("  -> Các dataset có trạng thái chưa thành công:")
                for d, s, c in errs:
                    print(f"     * Dataset: {d:<30} | Trạng thái: {s:<15} | Số lượng: {c:>6,}")
        else:
            print("  -> Không có bảng meta.crawl_progress trong DB này.")
        con.close()
    except Exception as e:
        print(f"  -> Lỗi kết nối hoặc truy vấn: {e}")
