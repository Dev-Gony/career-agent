from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.interfaces import (  # noqa: E402
    PROFILE_EXTERNAL_ANALYSIS_APPROVE_ACTION,
    build_slack_profile_analysis_consent_session,
    save_slack_profile_analysis_consent_session,
)
from career_agent.profile_input import (  # noqa: E402
    DEFAULT_GEMINI_DEVELOPMENT_MODEL,
    GeminiDevelopmentProfileAnalysisProvider,
    build_profile_text_extraction,
    save_profile_text_extraction,
)
from scripts import run_slack_socket  # noqa: E402
from tests.test_profile_text_extraction import _text_manifest  # noqa: E402


DECIDED_AT = datetime(2026, 9, 22, 10, tzinfo=timezone.utc)


def _request() -> dict:
    return {
        "slack_command_request": {
            "received_at": DECIDED_AT.isoformat(timespec="microseconds")
        },
        "source": {
            "team_id": "T01234567",
            "channel_id": "C01234567",
            "user_id": "U76543210",
            "thread_ts": "1789372700.000900",
        },
    }


class SlackProfileAnalysisConsentFlowTest(unittest.TestCase):
    def test_approval_is_saved_for_exact_extraction_without_candidate_text(self) -> None:
        manifest, content = _text_manifest(
            "## 경력\n- QA Engineer로 API 테스트 자동화를 수행했습니다.\n"
        )
        extraction = build_profile_text_extraction(
            manifest,
            content,
            extracted_at=DECIDED_AT,
        )
        session = build_slack_profile_analysis_consent_session(
            extraction,
            team_id="T01234567",
            channel_id="C01234567",
            user_id="U76543210",
            thread_ts="1789372700.000900",
            provider_name=GeminiDevelopmentProfileAnalysisProvider.provider_name,
            model_name=DEFAULT_GEMINI_DEVELOPMENT_MODEL,
            created_at=DECIDED_AT,
        )
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            extraction_directory = root_path / "extractions"
            session_directory = root_path / "sessions"
            consent_directory = root_path / "consents"
            save_profile_text_extraction(extraction, extraction_directory)
            save_slack_profile_analysis_consent_session(session, session_directory)
            with (
                patch.object(
                    run_slack_socket,
                    "DEFAULT_PROFILE_EXTRACTION_DIRECTORY",
                    extraction_directory,
                ),
                patch.object(
                    run_slack_socket,
                    "DEFAULT_SLACK_PROFILE_ANALYSIS_CONSENT_SESSION_DIRECTORY",
                    session_directory,
                ),
                patch.object(
                    run_slack_socket,
                    "DEFAULT_PROFILE_ANALYSIS_EXTERNAL_CONSENT_DIRECTORY",
                    consent_directory,
                ),
            ):
                result = run_slack_socket._run_profile_external_analysis_decision(
                    PROFILE_EXTERNAL_ANALYSIS_APPROVE_ACTION,
                    _request(),
                )
            consent_paths = list(
                consent_directory.glob("profile-analysis-external-consent-*.json")
            )
            stored_text = consent_paths[0].read_text(encoding="utf-8")

        self.assertEqual("approved", result["status"])
        self.assertEqual(1, len(consent_paths))
        self.assertNotIn(extraction["candidates"][0]["text"], stored_text)
        self.assertIn("무료 Gemini에는 실제 문서를 보내지 않으며", result["public_message"])


if __name__ == "__main__":
    unittest.main()
