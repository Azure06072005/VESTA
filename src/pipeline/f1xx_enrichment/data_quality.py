"""Backward-compatibility bridge for pipeline.data_quality.

Exposes DataQualityPipeline, generate_report, and main from
src.pipeline.ml.data_validation.data_quality.
"""
from __future__ import annotations

import sys
from pipeline.ml.data_validation.data_quality import (
    DQCheckResult,
    DataQualityPipeline,
    generate_report,
    main,
)

__all__ = ["DataQualityPipeline", "generate_report", "DQCheckResult", "main"]

if __name__ == "__main__":
    sys.exit(main())
