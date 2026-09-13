"""Pipeline Package for VESTA.

Structured into two primary tiers:
- f1xx_enrichment: Data Validation, Referential Integrity, Point-in-Time Joins & ML Features (F101-F104)
- f2xx_validation: Statistical Edge Validation, Robustness, DSR/PBO & Regime Audits (F201-F203)
"""
from __future__ import annotations

import pathlib
import sys

# Ensure src/ is in sys.path when pipeline is imported
_src_dir = str(pathlib.Path(__file__).resolve().parents[1])
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from . import f1xx_enrichment, f2xx_validation

__all__ = [
    "f1xx_enrichment",
    "f2xx_validation",
]
