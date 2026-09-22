from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.interfaces import (  # noqa: E402
    build_slack_profile_analysis_consent_session,
    save_slack_profile_analysis_consent_session,
)
from career_agent.profile_input import (  # noqa: E402
    ProfileDocumentError,
    analyze_profile_extraction_with_approved_external_consent,
    build_profile_analysis_external_consent,
    save_profile_analysis_external_consent,
)
from tests.test_profile_analysis_draft import (  # noqa: E402
    _extraction,
    _response,
)


NOW = datetime(2026, 9, 22, 12, tzinfo=timezone.utc)
SOURCE = {
    "team_id": "T01234567",
    "channel_id": "C01234567",
    "user_id": "U76543210",
    "thread_ts": "1789372700.000900",
}


class _Provider:
    provider_name = "google-gemini-development"
    model_name = "gemini-3.5-flash-lite"
    sends_data_externally = True

    def __init__(self) -> None:
        self.calls = 0

    def analyze(self, request, response_schema):
        self.calls += 1
        return _response()


class ProfileAnalysisExternalServiceTest(unittest.TestCase):
    def test_calls_provider_only_after_exact_approval(self) -> None:
        extraction = _extraction()
        provider = _Provider()
        session = build_slack_profile_analysis_consent_session(
            extraction,
            provider_name=provider.provider_name,
            model_name=provider.model_name,
            created_at=NOW,
            **SOURCE,
        )
        consent = build_profile_analysis_external_consent(
            extraction,
            provider_name=provider.provider_name,
            model_name=provider.model_name,
            consent_session_id=session["slack_profile_analysis_consent_session"][
                "session_id"
            ],
            decision="approve",
            decided_at=NOW + timedelta(minutes=1),
            **SOURCE,
        )
        with tempfile.TemporaryDirectory() as root:
            sessions = Path(root) / "sessions"
            consents = Path(root) / "consents"
            save_slack_profile_analysis_consent_session(session, sessions)
            save_profile_analysis_external_consent(consent, consents)
            draft = analyze_profile_extraction_with_approved_external_consent(
                extraction,
                provider,
                analyzed_at=NOW + timedelta(minutes=2),
                session_directory=sessions,
                consent_directory=consents,
            )

        self.assertEqual(1, provider.calls)
        self.assertEqual("external", draft["analysis_source"]["data_boundary"])

    def test_does_not_call_provider_without_approval(self) -> None:
        provider = _Provider()
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(ProfileDocumentError, "세션이 없음"):
                analyze_profile_extraction_with_approved_external_consent(
                    _extraction(),
                    provider,
                    analyzed_at=NOW,
                    session_directory=Path(root) / "sessions",
                    consent_directory=Path(root) / "consents",
                )

        self.assertEqual(0, provider.calls)


if __name__ == "__main__":
    unittest.main()
