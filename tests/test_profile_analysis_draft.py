from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.profile_input import (  # noqa: E402
    ProfileDocumentError,
    build_profile_analysis_draft,
    build_profile_analysis_request,
    profile_analysis_response_json_schema,
    save_profile_analysis_draft,
    validate_profile_analysis_response,
)


ANALYZED_AT = datetime(2026, 9, 20, 10, tzinfo=timezone.utc)


def _extraction() -> dict:
    document_id = "profile-document-resume-0123456789abcdef0123"
    texts = [
        "QA Engineer로 2022년부터 API 테스트 자동화를 수행했습니다.",
        "회귀 테스트 시간을 40% 단축했습니다.",
        "Python으로 테스트 데이터 검증 도구를 개발했습니다.",
    ]
    return {
        "profile_extraction": {
            "extraction_id": "profile-text-extraction-0123456789abcdef01234567",
            "status": "needs_review",
        },
        "source_document": {"document_id": document_id},
        "candidates": [
            {
                "candidate_id": f"candidate-{position:03d}",
                "profile_section": "career_history",
                "text": text,
                "status": "needs_review",
                "source_evidence": {
                    "document_id": document_id,
                    "line_start": position,
                    "line_end": position,
                },
            }
            for position, text in enumerate(texts, start=1)
        ],
        "metadata": {"schema_version": "0.1", "profile_updated": False},
    }


def _response() -> dict:
    return {
        "career_evidence": [
            {
                "role_or_context": "QA Engineer",
                "period_expression": "2022년",
                "responsibility_evidence": "API 테스트 자동화를 수행했습니다.",
                "candidate_ids": ["candidate-001"],
                "confidence": "high",
            }
        ],
        "achievement_evidence": [
            {
                "problem_evidence": None,
                "action_evidence": "회귀 테스트 시간을",
                "result_evidence": "40% 단축했습니다.",
                "candidate_ids": ["candidate-002"],
                "confidence": "high",
            }
        ],
        "technology_evidence": [
            {
                "technology_name": "Python",
                "usage_evidence": "Python으로 테스트 데이터 검증 도구를 개발했습니다.",
                "proficiency_status": "unconfirmed",
                "candidate_ids": ["candidate-003"],
                "confidence": "high",
            }
        ],
        "unknowns": [
            {
                "question": "Python을 실제 업무에서 얼마나 자주 사용했나요?",
                "reason": "원문만으로 사용 빈도와 숙련도를 확정할 수 없습니다.",
                "candidate_ids": ["candidate-003"],
                "confidence": "medium",
            }
        ],
    }


class ProfileAnalysisDraftTest(unittest.TestCase):
    def test_schema_is_strict_at_root_and_item_levels(self) -> None:
        schema = profile_analysis_response_json_schema()

        self.assertFalse(schema["additionalProperties"])
        career = schema["properties"]["career_evidence"]["items"]
        technology = schema["properties"]["technology_evidence"]["items"]
        self.assertFalse(career["additionalProperties"])
        self.assertEqual(
            ["unconfirmed"],
            technology["properties"]["proficiency_status"]["enum"],
        )

    def test_builds_review_only_draft_without_updating_extraction(self) -> None:
        extraction = _extraction()
        original = deepcopy(extraction)

        draft = build_profile_analysis_draft(
            extraction,
            _response(),
            analyzed_at=ANALYZED_AT,
            provider_name="synthetic",
            model_name="fixture-v1",
            data_boundary="local",
        )

        self.assertEqual(original, extraction)
        self.assertEqual("needs_review", draft["profile_analysis_draft"]["status"])
        self.assertEqual(
            {
                "career_evidence_count": 1,
                "achievement_evidence_count": 1,
                "technology_evidence_count": 1,
                "unknown_count": 1,
            },
            draft["summary"],
        )
        self.assertTrue(draft["metadata"]["provider_output_validated"])
        self.assertFalse(draft["metadata"]["profile_updated"])
        self.assertEqual(
            {
                "provider": "synthetic",
                "model": "fixture-v1",
                "data_boundary": "local",
            },
            draft["analysis_source"],
        )

    def test_builds_minimal_provider_request_without_document_metadata(self) -> None:
        request = build_profile_analysis_request(_extraction())
        serialized = json.dumps(request, ensure_ascii=False)

        self.assertEqual("0.1", request["contract_version"])
        self.assertEqual(3, len(request["candidates"]))
        self.assertNotIn("document_id", serialized)
        self.assertNotIn("line_start", serialized)
        self.assertNotIn("source_document", serialized)

    def test_rejects_reference_to_missing_candidate(self) -> None:
        response = _response()
        response["career_evidence"][0]["candidate_ids"] = ["candidate-999"]

        with self.assertRaisesRegex(ProfileDocumentError, "존재하지 않는 후보"):
            validate_profile_analysis_response(_extraction(), response)

    def test_rejects_text_not_present_in_referenced_candidates(self) -> None:
        response = _response()
        response["achievement_evidence"][0]["result_evidence"] = (
            "품질을 획기적으로 개선했습니다."
        )

        with self.assertRaisesRegex(ProfileDocumentError, "원문 구간"):
            validate_profile_analysis_response(_extraction(), response)

    def test_rejects_claimed_technology_proficiency(self) -> None:
        response = _response()
        response["technology_evidence"][0]["proficiency_status"] = "advanced"

        with self.assertRaisesRegex(ProfileDocumentError, "unconfirmed"):
            validate_profile_analysis_response(_extraction(), response)

    def test_rejects_additional_provider_field(self) -> None:
        response = _response()
        response["career_evidence"][0]["company_name"] = "Example Company"

        with self.assertRaisesRegex(ProfileDocumentError, "허용되지 않은 필드"):
            validate_profile_analysis_response(_extraction(), response)

    def test_rejects_naive_timestamp(self) -> None:
        with self.assertRaisesRegex(ProfileDocumentError, "시간대"):
            build_profile_analysis_draft(
                _extraction(),
                _response(),
                analyzed_at=datetime(2026, 9, 20, 10),
                provider_name="synthetic",
                model_name="fixture-v1",
                data_boundary="local",
            )

    def test_saves_and_reuses_identical_draft(self) -> None:
        first = build_profile_analysis_draft(
            _extraction(),
            _response(),
            analyzed_at=ANALYZED_AT,
            provider_name="synthetic",
            model_name="fixture-v1",
            data_boundary="local",
        )
        later = build_profile_analysis_draft(
            _extraction(),
            _response(),
            analyzed_at=ANALYZED_AT + timedelta(minutes=5),
            provider_name="synthetic",
            model_name="fixture-v1",
            data_boundary="local",
        )

        with tempfile.TemporaryDirectory() as directory:
            first_path, first_created = save_profile_analysis_draft(first, directory)
            later_path, later_created = save_profile_analysis_draft(later, directory)

        self.assertTrue(first_created)
        self.assertFalse(later_created)
        self.assertEqual(first_path, later_path)

    def test_rejects_tampered_existing_draft(self) -> None:
        draft = build_profile_analysis_draft(
            _extraction(),
            _response(),
            analyzed_at=ANALYZED_AT,
            provider_name="synthetic",
            model_name="fixture-v1",
            data_boundary="local",
        )
        with tempfile.TemporaryDirectory() as directory:
            path, _ = save_profile_analysis_draft(draft, directory)
            stored = json.loads(path.read_text(encoding="utf-8"))
            stored["summary"]["career_evidence_count"] = 99
            path.write_text(
                json.dumps(stored, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ProfileDocumentError, "내용이 일치하지 않음"):
                save_profile_analysis_draft(draft, directory)


if __name__ == "__main__":
    unittest.main()
