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
    build_profile_analysis_external_consent,
    load_profile_analysis_external_consent,
    profile_analysis_request_sha256,
    save_profile_analysis_external_consent,
    select_latest_profile_analysis_external_consent_for_session,
)
from tests.test_profile_analysis_draft import _extraction  # noqa: E402


DECIDED_AT = datetime(2026, 9, 22, 10, tzinfo=timezone.utc)
PROVIDER = "google-gemini-development"
MODEL = "gemini-3.5-flash-lite"
SESSION_ID = "slack-profile-analysis-consent-session-0123456789abcdef01234567"
SLACK_SOURCE = {
    "team_id": "T01234567",
    "channel_id": "C01234567",
    "user_id": "U76543210",
    "thread_ts": "1789372700.000900",
}


def _build(extraction: dict, *, decision: str, decided_at: datetime) -> dict:
    return build_profile_analysis_external_consent(
        extraction,
        provider_name=PROVIDER,
        model_name=MODEL,
        consent_session_id=SESSION_ID,
        **SLACK_SOURCE,
        decision=decision,
        decided_at=decided_at,
    )


class ProfileAnalysisExternalConsentTest(unittest.TestCase):
    def test_records_decision_without_copying_candidate_text(self) -> None:
        extraction = _extraction()
        consent = _build(extraction, decision="approve", decided_at=DECIDED_AT)

        serialized = json.dumps(consent, ensure_ascii=False)
        self.assertEqual(
            profile_analysis_request_sha256(extraction),
            consent["source"]["request_sha256"],
        )
        self.assertNotIn(extraction["candidates"][0]["text"], serialized)
        self.assertFalse(consent["metadata"]["contains_candidate_text"])
        self.assertFalse(consent["metadata"]["git_tracking_allowed"])

    def test_saves_and_selects_latest_decision(self) -> None:
        extraction = _extraction()
        first = _build(extraction, decision="reject", decided_at=DECIDED_AT)
        latest = _build(
            extraction,
            decision="approve",
            decided_at=DECIDED_AT + timedelta(minutes=1),
        )
        with tempfile.TemporaryDirectory() as directory:
            first_path = save_profile_analysis_external_consent(first, directory)
            save_profile_analysis_external_consent(latest, directory)
            loaded = load_profile_analysis_external_consent(first_path.stem, directory)
            selected = select_latest_profile_analysis_external_consent_for_session(
                SESSION_ID,
                directory,
            )

        self.assertEqual(first, loaded)
        self.assertEqual(latest, selected)

    def test_rejects_tampered_request_hash(self) -> None:
        consent = _build(
            _extraction(), decision="approve", decided_at=DECIDED_AT
        )
        tampered = deepcopy(consent)
        tampered["source"]["request_sha256"] = "0" * 64

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / (
                consent["profile_analysis_external_consent"]["consent_id"] + ".json"
            )
            path.write_text(json.dumps(tampered), encoding="utf-8")
            with self.assertRaisesRegex(ProfileDocumentError, "지문"):
                load_profile_analysis_external_consent(path.stem, directory)


if __name__ == "__main__":
    unittest.main()
