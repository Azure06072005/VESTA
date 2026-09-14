"""test_pipeline/f1xx_enrichment/test_incremental_streaming_ffd.py

Incremental Streaming Ingestion for Fractional Differentiation (FFD).
Implements an O(1) time-complexity ring buffer rolling update engine for daily streaming market data:
1. Mathematical Ring Buffer: Fixed-size circular buffer of width K (determined by tau = 1e-4).
2. O(1) Per-Bar Update: Calculates new FFD value via dot product with pre-reversed weights w[::-1],
   eliminating full-history batch convolution O(N * T * K).
3. Exact Equivalence: Guaranteed machine-precision parity (|X_stream - X_batch| < 1e-12).
4. Multi-Sector Orchestrator: Dynamically tracks 11 ICB sectors using sector-specific d* parameters.
5. Checkpointing: Full state serialization/deserialization for zero-loss recovery across restarts.
"""
from __future__ import annotations

from collections import deque
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple, Union

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from test_pipeline.f1xx_enrichment.test_fractional_differentiation import (
    get_weights_ffd,
    frac_diff_ffd,
)
from test_pipeline.f1xx_enrichment.test_sector_specific_fracdiff import (
    extract_sector_price_series,
    DB_PATH,
)

OUT_REPORT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../out/incremental_streaming_ffd_report.json")
)

SECTOR_OPTIMAL_D: Dict[str, float] = {
    "Ngân hàng": 0.25,
    "Tài chính": 0.25,
    "Công nghiệp": 0.20,
    "Dịch vụ Tiêu dùng": 0.20,
    "Nguyên vật liệu": 0.20,
    "Viễn thông": 0.20,
    "Công nghệ Thông tin": 0.15,
    "Dầu khí": 0.15,
    "Hàng Tiêu dùng": 0.15,
    "Dược phẩm và Y tế": 0.05,
    "Tiện ích Cộng đồng": 0.05,
}


class StreamingFFDCalculator:
    """O(1) Ring-Buffer Streaming Calculator for Fractional Differentiation."""

    def __init__(self, d: float, thres: float = 1e-4):
        self.d = float(d)
        self.thres = float(thres)
        # Chronological weights: w[0] corresponds to current bar, w[k] to lag k
        self.w = get_weights_ffd(self.d, thres=self.thres)
        self.K = len(self.w)
        # Precompute reversed weights for direct dot-product with chronological deque
        # Deque stores [X_{t - K + 1}, X_{t - K + 2}, ..., X_t]
        # So X_{t - k} aligns with w[k], meaning buffer aligns with w[::-1]
        self.w_rev = np.ascontiguousarray(self.w[::-1], dtype=np.float64)
        self.buffer: deque[float] = deque(maxlen=self.K)
        self.count: int = 0

    def prime(self, history: Union[List[float], np.ndarray, pd.Series]) -> int:
        """Primes buffer with historical observations.
        
        Only keeps the most recent K observations.
        Returns the number of observations currently in buffer.
        """
        vals = np.asarray(history, dtype=np.float64)
        # If history exceeds K, only take last K
        if len(vals) > self.K:
            vals = vals[-self.K:]
        self.buffer.clear()
        self.buffer.extend(vals)
        self.count = len(self.buffer)
        return len(self.buffer)

    def update(self, val: float) -> Optional[float]:
        """Ingests a single new price observation in O(1) time.
        
        Returns the new fractional differentiated value if buffer is full (K bars),
        or None if buffer is still warming up.
        """
        self.buffer.append(float(val))
        self.count += 1
        if len(self.buffer) < self.K:
            return None
        
        # Buffer has exactly K elements: [X_{t - K + 1}, ..., X_t]
        # w_rev has exactly K elements: [w_{K - 1}, ..., w_0]
        # dot product = sum_{k=0}^{K-1} w_k * X_{t-k}
        buf_arr = np.array(self.buffer, dtype=np.float64)
        return float(np.dot(self.w_rev, buf_arr))

    def get_state(self) -> Dict[str, Any]:
        """Serializes internal state for zero-loss checkpointing."""
        return {
            "d": self.d,
            "thres": self.thres,
            "K": self.K,
            "count": self.count,
            "buffer": list(self.buffer),
        }

    def restore_state(self, state: Dict[str, Any]) -> None:
        """Restores state from checkpoint."""
        assert self.d == state["d"], f"d mismatch: {self.d} vs {state['d']}"
        self.count = state["count"]
        self.buffer = deque(state["buffer"], maxlen=self.K)


class MultiSectorStreamingPipeline:
    """Orchestrates streaming FFD updates across all 11 ICB market sectors."""

    def __init__(self, sector_params: Dict[str, float] = SECTOR_OPTIMAL_D):
        self.calculators: Dict[str, StreamingFFDCalculator] = {
            sec: StreamingFFDCalculator(d=d) for sec, d in sector_params.items()
        }

    def prime_from_history(self, sector_history: Dict[str, pd.Series]) -> Dict[str, int]:
        """Primes all sector calculators with historical price series."""
        primed_counts = {}
        for sec, calc in self.calculators.items():
            if sec in sector_history:
                primed_counts[sec] = calc.prime(sector_history[sec])
            else:
                primed_counts[sec] = 0
        return primed_counts

    def process_streaming_bar(self, date: Any, sector_prices: Dict[str, float]) -> Dict[str, Optional[float]]:
        """Processes a single incoming multi-sector bar at end-of-day.
        
        Returns a dictionary mapping sector -> streaming FFD value.
        """
        results = {}
        for sec, calc in self.calculators.items():
            val = sector_prices.get(sec)
            if val is not None and not np.isnan(val):
                results[sec] = calc.update(val)
            else:
                results[sec] = None
        return results


def run_streaming_benchmark():
    """Runs rigorous benchmark comparing Batch vs Streaming FFD across 11 sectors."""
    print("=== RUNNING INCREMENTAL STREAMING INGESTION BENCHMARK ===")
    con = duckdb.connect(DB_PATH, read_only=True)
    sector_series = extract_sector_price_series(con)
    con.close()

    results_by_sector = {}
    total_batch_time = 0.0
    total_stream_time = 0.0

    # We evaluate over the Banking sector as prime benchmark
    bank_series = sector_series["Ngân hàng"]
    d_bank = SECTOR_OPTIMAL_D["Ngân hàng"]
    calc_bank = StreamingFFDCalculator(d=d_bank)
    K_bank = calc_bank.K

    print(f"[1] Banking Sector (d* = {d_bank}, Window K = {K_bank} bars):")
    
    # 1. Verification of Numerical Equivalence
    # Run Batch mode
    t0 = time.perf_counter()
    batch_res = frac_diff_ffd(bank_series, d=d_bank)
    t_batch = time.perf_counter() - t0

    # Run Streaming mode bar-by-bar
    t0 = time.perf_counter()
    stream_outputs = []
    stream_indices = []
    for dt, val in bank_series.items():
        res = calc_bank.update(val)
        if res is not None:
            stream_outputs.append(res)
            stream_indices.append(dt)
    t_stream = time.perf_counter() - t0

    stream_res = pd.Series(stream_outputs, index=stream_indices)

    # Align and test difference
    common_idx = batch_res.index.intersection(stream_res.index)
    diff = np.abs(batch_res.loc[common_idx] - stream_res.loc[common_idx])
    max_diff = float(diff.max())
    mean_diff = float(diff.mean())

    print(f"    - Total bars processed: {len(bank_series)}")
    print(f"    - Output bars: {len(common_idx)}")
    print(f"    - Max Absolute Difference: {max_diff:.2e} (Machine Precision Parity)")
    print(f"    - Mean Absolute Difference: {mean_diff:.2e}")
    assert max_diff < 1e-12, f"Streaming output diverged from batch! max_diff={max_diff}"

    # 2. Benchmark Time Complexity: Daily Incremental Simulation
    # Suppose we simulate streaming updates over the last 500 trading days
    sim_days = 500
    sub_series = bank_series.iloc[-sim_days:]
    initial_history = bank_series.iloc[:-sim_days]

    # Scenario A: Naive Daily Batch Recomputation (re-runs batch convolution every day as history grows)
    naive_batch_times = []
    curr_hist = list(initial_history.values)
    for val in sub_series.values:
        curr_hist.append(val)
        tb0 = time.perf_counter()
        _ = frac_diff_ffd(pd.Series(curr_hist), d=d_bank)
        naive_batch_times.append(time.perf_counter() - tb0)

    # Scenario B: Incremental Streaming Ring Buffer
    streaming_times = []
    stream_sim = StreamingFFDCalculator(d=d_bank)
    stream_sim.prime(initial_history)
    for val in sub_series.values:
        ts0 = time.perf_counter()
        _ = stream_sim.update(val)
        streaming_times.append(time.perf_counter() - ts0)

    avg_naive_batch_us = float(np.mean(naive_batch_times) * 1e6)
    avg_streaming_us = float(np.mean(streaming_times) * 1e6)
    speedup = avg_naive_batch_us / avg_streaming_us

    print(f"[2] Daily Ingestion Latency (Simulating {sim_days} consecutive days):")
    print(f"    - Naive Daily Full Batch Recompute: {avg_naive_batch_us:.2f} µs / bar")
    print(f"    - Incremental Streaming Ring Buffer: {avg_streaming_us:.2f} µs / bar")
    print(f"    - Speedup Factor: {speedup:.1f}x faster per bar (O(1) vs O(T))")

    # 3. Benchmark All 11 Sectors in MultiSectorStreamingPipeline
    pipeline = MultiSectorStreamingPipeline()
    # Prime pipeline with history up to 2024-01-01
    split_date = "2024-01-01"
    hist_dict = {sec: s.loc[:split_date] for sec, s in sector_series.items()}
    future_dict = {sec: s.loc[split_date:] for sec, s in sector_series.items()}
    pipeline.prime_from_history(hist_dict)

    # Get union of future dates
    future_dates = sorted(list(set.union(*[set(s.index) for s in future_dict.values()])))
    multi_streaming_times = []
    multi_records = []

    for dt in future_dates:
        daily_prices = {sec: future_dict[sec].get(dt, np.nan) for sec in SECTOR_OPTIMAL_D}
        t0 = time.perf_counter()
        ffd_vals = pipeline.process_streaming_bar(dt, daily_prices)
        multi_streaming_times.append(time.perf_counter() - t0)
        multi_records.append((dt, ffd_vals))

    avg_multi_us = float(np.mean(multi_streaming_times) * 1e6)
    print(f"[3] Multi-Sector Pipeline (All 11 Sectors simultaneously):")
    print(f"    - Throughput: {avg_multi_us:.2f} µs / daily market bar ({1e6 / avg_multi_us:,.0f} bars / second)")
    print(f"    - Max Latency across all days: {np.max(multi_streaming_times)*1e6:.2f} µs")

    # 4. Checkpoint Serialization / Deserialization Test
    chk = pipeline.calculators["Ngân hàng"].get_state()
    calc_restored = StreamingFFDCalculator(d=d_bank)
    calc_restored.restore_state(chk)
    # Feed same next value
    test_next_val = 2.50
    v1 = pipeline.calculators["Ngân hàng"].update(test_next_val)
    v2 = calc_restored.update(test_next_val)
    assert abs(v1 - v2) < 1e-15, "Checkpoint restore produced diverging output!"
    print("[4] Checkpointing & State Persistence: PASSED (Exact Bit-Level Equality)")

    # Save benchmark report
    report_data = {
        "benchmark_summary": {
            "banking_sector": {
                "d": d_bank,
                "window_K": K_bank,
                "max_diff_to_batch": max_diff,
                "naive_batch_latency_us": avg_naive_batch_us,
                "streaming_latency_us": avg_streaming_us,
                "speedup_factor": speedup,
            },
            "multi_sector_pipeline": {
                "total_sectors": len(SECTOR_OPTIMAL_D),
                "avg_latency_all_sectors_us": avg_multi_us,
                "throughput_bars_per_sec": float(1e6 / avg_multi_us),
            },
            "checkpoint_verification": "PASSED",
        },
        "sector_window_lengths": {sec: len(calc.w) for sec, calc in pipeline.calculators.items()},
    }

    os.makedirs(os.path.dirname(OUT_REPORT), exist_ok=True)
    with open(OUT_REPORT, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)

    print(f"[OK] Saved streaming benchmark report to: {OUT_REPORT}")


if __name__ == "__main__":
    run_streaming_benchmark()
