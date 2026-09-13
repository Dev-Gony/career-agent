"""End-to-end workflows composed from source and matching modules."""

from .greenhouse_analysis import (
    GreenhouseAnalysisError,
    analyze_greenhouse_job,
    build_persistable_match_result,
)

__all__ = [
    "GreenhouseAnalysisError",
    "analyze_greenhouse_job",
    "build_persistable_match_result",
]
