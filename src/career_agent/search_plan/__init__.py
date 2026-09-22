"""Build job discovery plans from verified profile facts."""

from .generator import (
    JOB_SEARCH_PLAN_RULES_VERSION,
    JOB_SEARCH_PLAN_SCHEMA_VERSION,
    JobSearchPlanError,
    build_job_search_plan,
)

__all__ = [
    "JOB_SEARCH_PLAN_RULES_VERSION",
    "JOB_SEARCH_PLAN_SCHEMA_VERSION",
    "JobSearchPlanError",
    "build_job_search_plan",
]
