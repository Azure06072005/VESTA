import sys
import duckdb
import pandas as pd

def check_performance():
    con = duckdb.connect("db/vesta.duckdb")
    
    print("--- F003 Crawl Performance Analysis ---")
    
    # Get summary of what was processed for F003 recently
    df = con.execute("""
        SELECT status, count(*) as count, min(last_attempt) as start_time, max(last_attempt) as end_time 
        FROM meta.crawl_progress 
        WHERE dataset_name = 'F003' 
        GROUP BY status
    """).df()
    
    if df.empty:
        print("No F003 crawl progress found.")
        return
        
    print("\nStatus Breakdown:")
    print(df[['status', 'count']].to_string(index=False))
    
    total_requests = df['count'].sum()
    min_time = df['start_time'].min()
    max_time = df['end_time'].max()
    delta_seconds = (max_time - min_time).total_seconds()
    
    if delta_seconds > 0:
        rpm = (total_requests / delta_seconds) * 60
        print(f"\nThroughput: {rpm:.1f} requests/minute")
        print(f"Total time elapsed: {delta_seconds:.1f} seconds")
        print(f"Total symbols processed: {total_requests}")
    else:
        print("\nNot enough time elapsed to calculate throughput.")
        
    # Get total records stored in news table
    try:
        news_count = con.execute("SELECT count(*) FROM core.news WHERE source='vnstock'").fetchone()[0]
        print(f"\nTotal news articles stored in core.news (vnstock source): {news_count}")
    except duckdb.CatalogException:
        print("\ncore.news table doesn't exist yet or has no vnstock records.")

if __name__ == "__main__":
    check_performance()
