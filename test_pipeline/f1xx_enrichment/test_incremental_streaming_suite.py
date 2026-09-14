"""test_pipeline/f1xx_enrichment/test_incremental_streaming_suite.py

Unit Test Suite for Incremental Streaming Ingestion (FFD Ring Buffer).
Verifies 4 mathematical and architectural invariants:
1. Exact Numerical Equivalence to Batch FFD (|diff| < 1e-12).
2. Constant O(1) Runtime Scaling (Per-bar latency invariant to history length T).
3. Ring Buffer Eviction Invariant (Values older than K bars have zero effect).
4. State Checkpoint Persistence & Cold-Start Recovery.
"""
from __future__ import annotations

import json
import os
import sys
import time
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from test_pipeline.f1xx_enrichment.test_fractional_differentiation import frac_diff_ffd
from test_pipeline.f1xx_enrichment.test_incremental_streaming_ffd import (
    StreamingFFDCalculator,
    MultiSectorStreamingPipeline,
    SECTOR_OPTIMAL_D,
)


class TestIncrementalStreamingFFD(unittest.TestCase):
    """Test suite ensuring streaming ring buffer correctness and invariants."""

    def setUp(self):
        np.random.seed(42)
        # Generate synthetic geometric random walk
        n = 1500
        returns = np.random.normal(0.0005, 0.015, n)
        self.prices = 100.0 * np.exp(np.cumsum(returns))
        self.series = pd.Series(self.prices)
        self.d = 0.25

    def test_streaming_numerical_equivalence_to_batch(self):
        """Invariant 1: Streaming ring buffer output must match batch convolution exactly (|diff| < 1e-12)."""
        calc = StreamingFFDCalculator(d=self.d)
        stream_vals = []
        for p in self.prices:
            out = calc.update(p)
            if out is not None:
                stream_vals.append(out)

        batch_series = frac_diff_ffd(self.series, d=self.d)
        batch_vals = batch_series.values

        self.assertEqual(len(stream_vals), len(batch_vals), "Output lengths must match")
        max_diff = np.max(np.abs(np.array(stream_vals) - batch_vals))
        self.assertLess(max_diff, 1e-12, f"Max difference {max_diff} exceeds machine tolerance")

    def test_constant_o1_runtime_scaling(self):
        """Invariant 2: Per-bar ingestion latency must remain O(1) regardless of history length T."""
        calc = StreamingFFDCalculator(d=self.d)
        # Prime with 500 bars
        calc.prime(self.prices[:500])

        # Benchmark phase 1: early history (T = 500 -> 1000)
        t0 = time.perf_counter()
        for p in self.prices[500:1000]:
            calc.update(p)
        time_phase1 = (time.perf_counter() - t0) / 500.0

        # Benchmark phase 2: deeper history (T = 1000 -> 1500)
        t0 = time.perf_counter()
        for p in self.prices[1000:1500]:
            calc.update(p)
        time_phase2 = (time.perf_counter() - t0) / 500.0

        # In O(1), time_phase2 should be approximately equal to time_phase1 (within noise margin < 2.5x)
        ratio = time_phase2 / time_phase1
        self.assertLess(ratio, 2.5, f"Scaling ratio {ratio:.2f} indicates non-O(1) complexity!")

    def test_ring_buffer_eviction_invariant(self):
        """Invariant 3: Observations older than K bars must be completely evicted with 0 weight."""
        calc = StreamingFFDCalculator(d=self.d)
        K = calc.K

        # Feed K random values
        warmup = np.random.uniform(50, 150, K)
        for val in warmup:
            calc.update(val)

        # Record state
        curr_output = calc.update(120.0)

        # Now create an alternate calculator where values before the last K were totally different
        calc2 = StreamingFFDCalculator(d=self.d)
        # Prepend 500 extreme values (e.g. 1,000,000)
        calc2.prime(np.ones(500) * 1000000.0)
        # Then feed the exact same last K values
        for val in warmup:
            calc2.update(val)
        curr_output2 = calc2.update(120.0)

        self.assertAlmostEqual(
            curr_output,
            curr_output2,
            places=10,
            msg="Old evicted values corrupted current FFD output!",
        )

    def test_checkpoint_serialization_and_recovery(self):
        """Invariant 4: Serializing and restoring state must produce identical streaming stream."""
        pipeline = MultiSectorStreamingPipeline()
        # Feed 600 bars of synthetic data for all sectors
        for i in range(600):
            mock_bar = {sec: self.prices[i] * (1.0 + 0.01 * idx) for idx, sec in enumerate(SECTOR_OPTIMAL_D)}
            pipeline.process_streaming_bar(f"2026-01-{i:03d}", mock_bar)

        # Save checkpoint for 'Ngân hàng'
        state_dict = pipeline.calculators["Ngân hàng"].get_state()
        state_json = json.dumps(state_dict)

        # Create fresh calculator from JSON
        recovered_calc = StreamingFFDCalculator(d=pipeline.calculators["Ngân hàng"].d)
        recovered_calc.restore_state(json.loads(state_json))

        # Feed next 50 bars and compare outputs
        for i in range(600, 650):
            test_val = self.prices[i]
            orig_out = pipeline.calculators["Ngân hàng"].update(test_val)
            rec_out = recovered_calc.update(test_val)
            self.assertAlmostEqual(orig_out, rec_out, places=12)


if __name__ == "__main__":
    unittest.main()
