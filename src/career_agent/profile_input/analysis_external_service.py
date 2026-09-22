"""Run one external profile analysis only after exact consent validation."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from .analysis_external_authorization import (
    require_approved_profile_analysis_external_consent,
)
from .analysis_service import ProfileAnalysisProvider, analyze_profile_extraction


def analyze_profile_extraction_with_approved_external_consent(
    extraction: Mapping[str, Any],
    provider: ProfileAnalysisProvider,
    *,
    analyzed_at: datetime,
    session_directory: str | Path,
    consent_directory: str | Path,
) -> dict[str, Any]:
    """Validate the latest exact approval, then call the external provider."""

    require_approved_profile_analysis_external_consent(
        extraction,
        provider_name=provider.provider_name,
        model_name=provider.model_name,
        session_directory=session_directory,
        consent_directory=consent_directory,
    )
    return analyze_profile_extraction(
        extraction,
        provider,
        analyzed_at=analyzed_at,
        external_transfer_approved=True,
    )
