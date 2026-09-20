"""Orchestrate profile analysis without binding the domain to one provider."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Protocol

from .analysis_draft import (
    build_profile_analysis_draft,
    build_profile_analysis_request,
    profile_analysis_response_json_schema,
)
from .document_store import ProfileDocumentError


class ProfileAnalysisProvider(Protocol):
    """Minimal contract for local fixtures and future external LLM providers."""

    provider_name: str
    model_name: str
    sends_data_externally: bool

    def analyze(
        self,
        request: Mapping[str, Any],
        response_schema: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Return one response that follows the supplied strict JSON Schema."""


def analyze_profile_extraction(
    extraction: Mapping[str, Any],
    provider: ProfileAnalysisProvider,
    *,
    analyzed_at: datetime,
    external_transfer_approved: bool = False,
) -> dict[str, Any]:
    """Call one provider and build a grounded, review-only analysis draft."""

    sends_data_externally = provider.sends_data_externally
    if not isinstance(sends_data_externally, bool):
        raise ProfileDocumentError("provider.sends_data_externally는 bool이어야 함")
    if sends_data_externally and external_transfer_approved is not True:
        raise ProfileDocumentError("외부 LLM 전송 승인이 필요함")
    request = build_profile_analysis_request(extraction)
    response = provider.analyze(
        request,
        profile_analysis_response_json_schema(),
    )
    if not isinstance(response, Mapping):
        raise ProfileDocumentError("프로필 분석 공급자 응답 객체가 필요함")
    return build_profile_analysis_draft(
        extraction,
        response,
        analyzed_at=analyzed_at,
        provider_name=provider.provider_name,
        model_name=provider.model_name,
        data_boundary="external" if sends_data_externally else "local",
    )
