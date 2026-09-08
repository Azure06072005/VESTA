"""Pre-F201 readiness check, run together rather than assumed.

Two independent questions:
1. Does a sentiment scorer/lexicon already exist in the repo (real code,
   real source citation), or is this still the unresolved "unsourced
   stated assumption" placeholder flagged in project memory?
2. What does core.news / core.pit_events actually contain right now in
   terms of REAL, sentiment-bearing editorial text -- not just row
   counts, but a genuine sample check, given this session's history of
   disclosure-headline-dominated corpora (F003: 100% disclosures:
   confirmed 2026-08-31/09-02; F004: 99.99% disclosures, only 51 real
   editorial rows as of the F004c purge).

Usage:
    ./.venv/bin/python scratch/check_f201_readiness.py --db db/vesta.duckdb
"""
from __future__ import annotations

import argparse
import pathlib
import re
import subprocess


def check_sentiment_code_exists(repo_root: pathlib.Path) -> None:
    print("=== 1. Searching for existing sentiment scorer / lexicon code ===")
    candidates = [
        "sentiment", "lexicon", "vader", "polarity", "sentiwordnet",
    ]
    hits = []
    src_dir = repo_root / "src"
    py_files = list(src_dir.rglob("*.py"))
    for py_file in py_files:
        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore").lower()
            for pattern in candidates:
                if pattern in content:
                    hits.append((pattern, str(py_file.relative_to(repo_root))))
        except Exception as e:
            print(f"  (read failed for {py_file}: {e})")

    if not hits:
        print("  NOTHING FOUND -- no sentiment scorer or lexicon file exists in src/ at all.")
        print("  This means F201's core dependency (B3: 'numbers need a source') is")
        print("  still the unresolved placeholder from project memory, not a solved item.")
    else:
        print(f"  Found {len(hits)} file(s) mentioning sentiment-related terms:")
        for pattern, path in hits:
            print(f"    [{pattern}] {path}")
        print("  --> Open each of these and check whether the lexicon/method has a")
        print("      real citation (a paper, a published VN finance lexicon, or a")
        print("      documented methodology) vs. an ad-hoc keyword list with no source.")


def check_news_text_readiness(db_path: str) -> None:
    print("\n=== 2. Real sentiment-bearing text readiness in core.news ===")
    try:
        import duckdb
    except ImportError:
        print("  duckdb not installed in this environment -- run this section manually.")
        return

    con = duckdb.connect(db_path, read_only=True)

    total = con.execute("SELECT COUNT(*) FROM core.news").fetchone()[0]
    with_real_body = con.execute(
        "SELECT COUNT(*) FROM core.news WHERE body IS NOT NULL AND LENGTH(body) > 200"
    ).fetchone()[0]
    print(f"  Total core.news rows: {total:,}")
    print(f"  Rows with a real, substantial body (>200 chars): {with_real_body:,} "
          f"({with_real_body/total*100:.3f}% of total)")

    by_source = con.execute(
        "SELECT source, COUNT(*), COUNT(*) FILTER (WHERE body IS NOT NULL AND LENGTH(body) > 200) "
        "FROM core.news GROUP BY source"
    ).fetchall()
    print("  By source:")
    for src, cnt, real_body_cnt in by_source:
        print(f"    {src:10s}: {cnt:>8,} total, {real_body_cnt:>6,} with real body")

    # Check pit_events specifically, since that's what F201 would actually read
    try:
        pit_total = con.execute("SELECT COUNT(*) FROM core.pit_events").fetchone()[0]
        pit_with_headline_only = con.execute(
            "SELECT COUNT(*) FROM core.pit_events"
        ).fetchone()[0]
        print(f"\n  core.pit_events total rows: {pit_total:,}")
        cols = [r[0] for r in con.execute("DESCRIBE core.pit_events").fetchall()]
        print(f"  core.pit_events columns: {cols}")
        if "sentiment" in cols:
            sentiment_populated = con.execute(
                "SELECT COUNT(*) FROM core.pit_events WHERE sentiment IS NOT NULL"
            ).fetchone()[0]
            print(f"  Rows with sentiment ALREADY populated: {sentiment_populated:,} "
                  f"(should be 0 per F102's original spec -- sentiment is F201's job to fill)")
    except Exception as e:
        print(f"  core.pit_events check failed: {e}")

    con.close()

    print("\n  Interpretation: if 'rows with real body' is a tiny fraction of total,")
    print("  running a sentiment scorer over headline text alone (for the disclosure-")
    print("  dominated majority) is a fundamentally different, weaker signal than")
    print("  scoring real article text -- this affects what F201's result would even mean.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()

    check_sentiment_code_exists(pathlib.Path(args.repo_root))
    check_news_text_readiness(args.db)


if __name__ == "__main__":
    main()