"""Profile and job-posting matching functions."""

from .eligibility import EligibilityMatchError, assess_eligibility
from .experience import ExperienceMatchError, match_experience_requirements
from .insights import MatchInsightsError, build_match_insights
from .recommendation import RecommendationError, build_application_recommendation
from .responsibility import ResponsibilityMatchError, match_responsibilities
from .service import RequirementMatchError, match_job_requirements
from .technology import TechnologyMatchError, match_technology_requirements

__all__ = [
    "EligibilityMatchError",
    "assess_eligibility",
    "ExperienceMatchError",
    "match_experience_requirements",
    "MatchInsightsError",
    "build_match_insights",
    "RecommendationError",
    "build_application_recommendation",
    "ResponsibilityMatchError",
    "match_responsibilities",
    "RequirementMatchError",
    "match_job_requirements",
    "TechnologyMatchError",
    "match_technology_requirements",
]
