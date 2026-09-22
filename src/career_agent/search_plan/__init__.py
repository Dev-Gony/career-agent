"""Build job discovery plans from verified profile facts."""

from .generator import (
    JOB_SEARCH_PLAN_RULES_VERSION,
    JOB_SEARCH_PLAN_SCHEMA_VERSION,
    JobSearchPlanError,
    build_job_search_plan,
)
from .validation import (
    validate_job_search_plan,
    validate_job_search_plan_for_profile,
)
from .search_focus import (
    MAX_SEARCH_FOCUS_ROLES,
    MAX_SEARCH_FOCUS_ROLE_CHARS,
    MAX_SEARCH_FOCUS_TOTAL_CHARS,
    validate_search_focus_roles,
)

__all__ = [
    "JOB_SEARCH_PLAN_RULES_VERSION",
    "JOB_SEARCH_PLAN_SCHEMA_VERSION",
    "JobSearchPlanError",
    "build_job_search_plan",
    "validate_job_search_plan",
    "validate_job_search_plan_for_profile",
    "MAX_SEARCH_FOCUS_ROLES",
    "MAX_SEARCH_FOCUS_ROLE_CHARS",
    "MAX_SEARCH_FOCUS_TOTAL_CHARS",
    "validate_search_focus_roles",
]
