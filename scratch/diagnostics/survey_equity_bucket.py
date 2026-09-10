"""Full survey of the cafef directory's remaining 'equity' bucket after
warrant/bond/fund exclusion -- catches a fourth (or fifth...) hidden
instrument category the same way warrants, bonds, and funds were each
found: by looking at ALL rows, not a 10-row sample that happened to look
clean.

This does NOT replace parse_directory()'s tested classification -- it's a
diagnostic to run BEFORE trusting the 'equity' bucket for anything, and
before any --write step. If it finds a new pattern, that becomes a new
_instrument_type() case + test, the same way this happened three times
already (warrants, bonds, funds).

Usage:
    ./.venv/bin/python scratch/survey_equity_bucket.py --cafef-json scratch/cafef_company_list.json
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from collections import Counter

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from crawlers.cafef_symbol_directory import parse_directory

# First-word / first-two-word prefixes that are KNOWN, real Vietnamese
# corporate-entity forms -- confirmed by direct inspection of the real
# directory, not guessed. Anything in the 'equity' bucket NOT starting
# with one of these is flagged for manual review rather than silently
# trusted.
KNOWN_EQUITY_PREFIXES = (
    "Công ty Cổ phần",
    "Công ty cổ phần",
    "CTCP",
    "Công ty TNHH",
    "Tổng Công ty",
    "Tổng công ty",
    "Tập đoàn",
    "Ngân hàng",  # banks, e.g. "Ngân hàng TMCP..."
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cafef-json", required=True)
    args = parser.parse_args()

    raw_entries = json.loads(pathlib.Path(args.cafef_json).read_text(encoding="utf-8"))
    df = parse_directory(raw_entries)

    print("=== instrument_type breakdown (full directory) ===")
    print(df["instrument_type"].value_counts().to_string())

    equities = df[df["instrument_type"] == "equity"]
    print(f"\n=== Surveying all {len(equities)} 'equity' rows for hidden categories ===")

    unrecognized = equities[~equities["org_name"].str.startswith(KNOWN_EQUITY_PREFIXES)]
    print(f"\nRows NOT matching any KNOWN_EQUITY_PREFIXES: {len(unrecognized)}")

    if len(unrecognized) == 0:
        print("None -- every 'equity' row starts with a recognized corporate-entity "
              "prefix. No evidence of a hidden 4th category.")
    else:
        print("These need manual review -- do NOT assume they're all legitimate "
              "equities just because they weren't caught by warrant/bond/fund rules:\n")
        # Show frequency of first word, to spot a pattern quickly rather than
        # reading every row individually.
        first_words = Counter(name.strip().split()[0] for name in unrecognized["org_name"])
        print("First-word frequency among unrecognized rows:")
        for word, count in first_words.most_common(20):
            print(f"  {word:20s} {count}")
        print("\nFull list of unrecognized rows (symbol, exchange, org_name):")
        print(
            unrecognized[["symbol", "exchange", "org_name"]]
            .to_string(index=False, max_rows=None)
        )

    print(
        "\n(Reminder: 'unrecognized prefix' does not automatically mean "
        "'not an equity' -- e.g. a foreign-invested company or a co-operative "
        "might use a different legal-entity phrase. This survey exists to "
        "surface candidates for a human decision, not to auto-classify them.)"
    )


if __name__ == "__main__":
    main()