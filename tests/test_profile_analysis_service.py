from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest
from typing import Any, Mapping


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.profile_input import (  # noqa: E402
    ProfileDocumentError,
    analyze_profile_extraction,
)


ANALYZED_AT = datetime(2026, 9, 20, 11, tzinfo=timezone.utc)


def _extraction() -> dict:
    document_id = "profile-document-resume-0123456789abcdef0123"
    return {
        "profile_extraction": {
            "extraction_id": "profile-text-extraction-0123456789abcdef01234567",
            "status": "needs_review",
        },
        "source_document": {"document_id": document_id},
        "candidates": [
            {
                "candidate_id": "candidate-001",
                "profile_section": "skills",
                "text": "Python으로 API 테스트 도구를 개발했습니다.",
                "status": "needs_review",
                "source_evidence": {
                    "document_id": document_id,
                    "line_start": 1,
                    "line_end": 1,
                },
            }
        ],
        "metadata": {"schema_version": "0.1", "profile_updated": False},
    }


def _response() -> dict:
    return {
        "career_evidence": [],
        "achievement_evidence": [],
        "technology_evidence": [
            {
                "technology_name": "Python",
                "usage_evidence": "Python으로 API 테스트 도구를 개발했습니다.",
                "proficiency_status": "unconfirmed",
                "candidate_ids": ["candidate-001"],
                "confidence": "high",
            }
        ],
        "unknowns": [],
    }


class RecordingProvider:
    provider_name = "synthetic"
    model_name = "fixture-v1"

    def __init__(self, *, external: bool, response: Any = None) -> None:
        self.sends_data_externally = external
        self.response = _response() if response is None else response
        self.calls: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []

    def analyze(
        self,
        request: Mapping[str, Any],
        response_schema: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        self.calls.append((deepcopy(request), deepcopy(response_schema)))
        return self.response


class ProfileAnalysisServiceTest(unittest.TestCase):
    def test_runs_local_provider_through_grounded_draft_boundary(self) -> None:
        provider = RecordingProvider(external=False)

        draft = analyze_profile_extraction(
            _extraction(),
            provider,
            analyzed_at=ANALYZED_AT,
        )

        self.assertEqual(1, len(provider.calls))
        request, schema = provider.calls[0]
        self.assertEqual(["candidate-001"], [item["candidate_id"] for item in request["candidates"]])
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual("local", draft["analysis_source"]["data_boundary"])
        self.assertFalse(draft["metadata"]["profile_updated"])

    def test_blocks_external_provider_before_call_without_explicit_approval(self) -> None:
        provider = RecordingProvider(external=True)

        with self.assertRaisesRegex(ProfileDocumentError, "외부 LLM 전송 승인"):
            analyze_profile_extraction(
                _extraction(),
                provider,
                analyzed_at=ANALYZED_AT,
            )

        self.assertEqual([], provider.calls)

    def test_allows_external_provider_after_explicit_approval(self) -> None:
        provider = RecordingProvider(external=True)

        draft = analyze_profile_extraction(
            _extraction(),
            provider,
            analyzed_at=ANALYZED_AT,
            external_transfer_approved=True,
        )

        self.assertEqual(1, len(provider.calls))
        self.assertEqual("external", draft["analysis_source"]["data_boundary"])

    def test_rejects_non_object_provider_response(self) -> None:
        provider = RecordingProvider(external=False, response=[])

        with self.assertRaisesRegex(ProfileDocumentError, "공급자 응답 객체"):
            analyze_profile_extraction(
                _extraction(),
                provider,
                analyzed_at=ANALYZED_AT,
            )


if __name__ == "__main__":
    unittest.main()
