"""Forwarding shim for pipeline.f2xx_validation.f203_regime_audit (F203)."""
from __future__ import annotations

from pipeline.f2xx_validation.f203_regime_audit import (
    REGIMES_16,
    RegimeStats,
    get_db_connection,
    load_sanitized_pit_events,
    main,
    run_regime_audit,
)

__all__ = [
    "REGIMES_16",
    "RegimeStats",
    "get_db_connection",
    "load_sanitized_pit_events",
    "main",
    "run_regime_audit",
]

if __name__ == "__main__":
    main()
