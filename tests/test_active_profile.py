from __future__ import annotations

from datetime import timedelta
import json
from pathlib import Path
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.profile_input import (  # noqa: E402
    ProfileDocumentError,
    build_profile_activation,
    build_profile_analysis_application,
    build_profile_analysis_final_review,
    resolve_active_profile_path,
    save_profile_activation,
    save_profile_analysis_application,
)
from tests.test_profile_analysis_application import _final  # noqa: E402
from tests.test_profile_analysis_update_proposal import CREATED_AT  # noqa: E402


def _applied() -> tuple[dict, dict]:
    profile, final = _final()
    review = build_profile_analysis_final_review(
        final,
        decision="approve",
        reviewed_at=CREATED_AT + timedelta(minutes=30),
    )
    application, updated = build_profile_analysis_application(
        profile,
        final,
        review,
        applied_at=CREATED_AT + timedelta(minutes=31),
    )
    assert updated is not None
    return application, updated


class ActiveProfileTest(unittest.TestCase):
    def test_resolves_verified_activation_to_fixed_private_profile(self) -> None:
        application, profile = _applied()
        activation = build_profile_activation(
            application,
            profile,
            activated_at=CREATED_AT + timedelta(minutes=32),
        )
        with tempfile.TemporaryDirectory() as root:
            activation_directory = Path(root) / "activations"
            application_directory = Path(root) / "applications"
            save_profile_analysis_application(application, profile, application_directory)
            save_profile_activation(activation, activation_directory)
            path = resolve_active_profile_path(activation_directory, application_directory)
            loaded = json.loads(path.read_text(encoding="utf-8")) if path else None

        self.assertEqual(profile, loaded)
        self.assertFalse(activation["metadata"]["contains_profile_content"])

    def test_returns_none_without_activation_and_rejects_tampered_profile(self) -> None:
        application, profile = _applied()
        activation = build_profile_activation(
            application,
            profile,
            activated_at=CREATED_AT + timedelta(minutes=32),
        )
        with tempfile.TemporaryDirectory() as root:
            activation_directory = Path(root) / "activations"
            application_directory = Path(root) / "applications"
            self.assertIsNone(
                resolve_active_profile_path(activation_directory, application_directory)
            )
            application_path, _ = save_profile_analysis_application(
                application,
                profile,
                application_directory,
            )
            save_profile_activation(activation, activation_directory)
            profile_path = application_path.parent / "profile.json"
            tampered = json.loads(profile_path.read_text(encoding="utf-8"))
            tampered["profile"]["career_goals"]["primary_goal"] = "변조"
            profile_path.write_text(json.dumps(tampered), encoding="utf-8")
            with self.assertRaisesRegex(ProfileDocumentError, "지문"):
                resolve_active_profile_path(activation_directory, application_directory)


if __name__ == "__main__":
    unittest.main()
