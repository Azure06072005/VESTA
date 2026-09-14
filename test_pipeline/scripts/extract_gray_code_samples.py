"""Extracts raw representative data samples for Module 1: Gray Code Encoding.

Updated with Canonical REGIME_BOUNDARIES, Scope Topology, and Historical Shocks Catalog.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

import duckdb
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from test_pipeline.f1xx_enrichment.test_gray_code_encoding import (
    HISTORICAL_SUB_EVENTS,
    REGIME_BOUNDARIES,
    SCOPE_TO_GRAY,
    encode_macro_state_gray,
    hamming_distance,
    int_to_binary_bits,
    int_to_gray_bits,
    map_date_to_regime_info,
)


def extract_samples():
    print("=" * 90)
    print("TABLE 1: 16 CANONICAL REGIMES WITH SCOPE & 6-BIT COMBINED GRAY CODE")
    print("=" * 90)

    rows = []
    n_regimes = len(REGIME_BOUNDARIES)
    for i in range(n_regimes):
        r_name, start_d, end_d, scope = REGIME_BOUNDARIES[i]
        bin_bits = "".join(map(str, int_to_binary_bits(i, 4)))
        gray_r_bits = "".join(map(str, int_to_gray_bits(i, 4)))
        gray_s_bits = "".join(map(str, SCOPE_TO_GRAY[scope]))
        combined_6b = gray_r_bits + gray_s_bits

        if i < n_regimes - 1:
            h_bin = hamming_distance(int_to_binary_bits(i, 4), int_to_binary_bits(i + 1, 4))
            h_gray = hamming_distance(int_to_gray_bits(i, 4), int_to_gray_bits(i + 1, 4))
        else:
            h_bin = "-"
            h_gray = "-"

        rows.append({
            "Idx": i,
            "Regime Name": r_name,
            "Window": f"{start_d} -> {end_d}",
            "Scope": scope,
            "Gray(4b)": gray_r_bits,
            "Scope(2b)": gray_s_bits,
            "Combined(6b)": combined_6b,
            "Adj H": h_gray,
        })

    df_table1 = pd.DataFrame(rows)
    print(df_table1.to_string(index=False))

    print("\n" + "=" * 90)
    print("TABLE 2: CONCRETE HISTORICAL TRANSMISSION SHOCKS CATALOG (SUB-REGIMES)")
    print("=" * 90)

    sub_rows = []
    for sub in HISTORICAL_SUB_EVENTS:
        sub_rows.append({
            "Event ID": sub["event_id"],
            "Period": f"{sub['start_date']} -> {sub['end_date']}",
            "Scope": sub["scope"],
            "Transmission Channel": sub["channel"],
            "Parent Regime": sub["parent_regime"],
            "Impact Summary": sub["impact_summary"][:55] + "...",
        })
    df_table2 = pd.DataFrame(sub_rows)
    print(df_table2.to_string(index=False))

    print("\n" + "=" * 90)
    print("TABLE 3: DUCKDB REAL EVENTS ENRICHED WITH 6-BIT MACRO GRAY VECTOR & ACTIVE SHOCKS")
    print("=" * 90)

    con = duckdb.connect("db/test_db/vesta_test.duckdb", read_only=True)
    df_events = con.execute("""
        SELECT symbol, published_at, CAST(published_at AS DATE) AS effective_date, headline, price_at_publish
        FROM core.pit_events
        WHERE headline IS NOT NULL AND published_at IS NOT NULL
        ORDER BY published_at DESC
        LIMIT 10
    """).df()
    con.close()

    enriched_records = [encode_macro_state_gray(d) for d in df_events["effective_date"]]
    df_enriched = pd.DataFrame(enriched_records)

    df_events["regime_id"] = df_enriched["regime_id"]
    df_events["scope"] = df_enriched["scope"]
    df_events["macro_gray_6b"] = df_enriched["macro_gray_str"]
    df_events["active_shocks"] = df_enriched["active_sub_events"].apply(lambda s: ", ".join(s) if s else "None")
    df_events["headline_snippet"] = df_events["headline"].apply(lambda h: (h[:40] + "...") if len(h) > 40 else h)

    display_cols = ["symbol", "effective_date", "regime_id", "scope", "macro_gray_6b", "active_shocks", "headline_snippet"]
    print(df_events[display_cols].to_string(index=False))


if __name__ == "__main__":
    extract_samples()
