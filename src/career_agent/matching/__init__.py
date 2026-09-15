"""Profile and job-posting matching functions."""

from .eligibility import EligibilityMatchError, assess_eligibility
from .experience import ExperienceMatchError, match_experience_requirements
from .insights import MatchInsightsError, build_match_insights
from .job_posting_information import (
    JobPostingInformationError,
    assess_job_posting_information,
)
from .learning import LearningRecommendationError, build_learning_recommendations
from .portfolio import PortfolioRecommendationError, build_portfolio_recommendations
from .recommendation import RecommendationError, build_application_recommendation
from .responsibility import ResponsibilityMatchError, match_responsibilities
from .service import (
    MATCHING_RULES_VERSION,
    RequirementMatchError,
    match_job_requirements,
)
from .technology import TechnologyMatchError, match_technology_requirements

__all__ = [
    "EligibilityMatchError",
    "assess_eligibility",
    "ExperienceMatchError",
    "match_experience_requirements",
    "MatchInsightsError",
    "build_match_insights",
    "JobPostingInformationError",
    "assess_job_posting_information",
    "LearningRecommendationError",
    "build_learning_recommendations",
    "PortfolioRecommendationError",
    "build_portfolio_recommendations",
    "RecommendationError",
    "build_application_recommendation",
    "ResponsibilityMatchError",
    "match_responsibilities",
    "RequirementMatchError",
    "MATCHING_RULES_VERSION",
    "match_job_requirements",
    "TechnologyMatchError",
    "match_technology_requirements",
]
