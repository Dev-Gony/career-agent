"""Convert permitted external job sources into the internal posting schema."""

from .greenhouse import (
    GreenhouseJobError,
    build_greenhouse_job_posting,
    fetch_greenhouse_job,
)

__all__ = [
    "GreenhouseJobError",
    "build_greenhouse_job_posting",
    "fetch_greenhouse_job",
]
