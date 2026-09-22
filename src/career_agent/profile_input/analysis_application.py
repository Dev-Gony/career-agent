"""Apply one explicitly approved final analysis proposal to a new profile version."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Mapping

from .analysis_final_proposal import validate_profile_analysis_final_proposal
from .analysis_final_review import validate_profile_analysis_final_review
from .document_store import ProfileDocumentError
from .skill_mapping import normalize_skill_name
from .update_proposal import profile_content_sha256


PROFILE_ANALYSIS_APPLICATION_SCHEMA_VERSION = "0.1"
PROFILE_ANALYSIS_APPLICATION_RULES_VERSION = "0.1"
_APPLICATION_ID_PATTERN = re.compile(r"^profile-analysis-application-[0-9a-f]{24}$")


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProfileDocumentError(f"{name} 객체가 필요함")
    return value


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProfileDocumentError(f"{name} 문자열이 필요함")
    return value.strip()


def build_profile_analysis_application(
    profile_document: Mapping[str, Any],
    final_proposal: Mapping[str, Any],
    final_review: Mapping[str, Any],
    *,
    applied_at: datetime,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Create an audit record and an optional separate updated profile document."""

    if applied_at.tzinfo is None or applied_at.utcoffset() is None:
        raise ProfileDocumentError("applied_at은 시간대가 포함되어야 함")
    proposal = validate_profile_analysis_final_proposal(final_proposal)
    review = validate_profile_analysis_final_review(final_review)
    proposal_root = proposal["profile_analysis_final_proposal"]
    review_root = review["profile_analysis_final_review"]
    review_source = review["source"]
    base_hash = profile_content_sha256(profile_document)
    if (
        proposal_root["base_profile_content_sha256"] != base_hash
        or review_source["base_profile_content_sha256"] != base_hash
    ):
        raise ProfileDocumentError("최종 변경안 생성 또는 검토 뒤 기준 프로필이 변경됨")
    if (
        review_source["final_proposal_id"] != proposal_root["final_proposal_id"]
        or review_source["base_profile_id"] != proposal_root["base_profile_id"]
    ):
        raise ProfileDocumentError("최종 검토 기록이 변경안과 일치하지 않음")

    updated_profile: dict[str, Any] | None = None
    applied_items: list[dict[str, str]] = []
    output_hash: str | None = None
    if review_root["decision"] == "approve":
        updated_profile = deepcopy(dict(profile_document))
        profile = _mapping(updated_profile.get("profile"), "profile")
        if not isinstance(profile, dict):
            raise ProfileDocumentError("profile은 수정 가능한 객체여야 함")
        careers = profile.get("career_history")
        skills = profile.get("skills")
        if not isinstance(careers, list) or not isinstance(skills, list):
            raise ProfileDocumentError("profile 경력과 기술 배열이 필요함")
        career_index = {
            _text(_mapping(item, "career item").get("career_id"), "career_id"): item
            for item in careers
        }
        skill_index = {
            _text(_mapping(item, "skill item").get("skill_id"), "skill_id"): item
            for item in skills
        }
        skill_names = {
            normalize_skill_name(_text(_mapping(item, "skill item").get("name"), "skill.name"))
            for item in skills
        }
        for raw_change in proposal["resolved_changes"]:
            change = _mapping(raw_change, "resolved_change")
            change_id = _text(change.get("change_id"), "change_id")
            target = _mapping(change.get("target"), "change.target")
            value = _mapping(change.get("proposed_value"), "change.proposed_value")
            record_id = _text(target.get("record_id"), "change.target.record_id")
            operation = target.get("operation")
            if operation == "append_responsibility_evidence":
                career = career_index.get(record_id)
                if not isinstance(career, dict):
                    raise ProfileDocumentError("최종 변경안의 대상 경력이 현재 프로필에 없음")
                responsibilities = career.get("responsibilities")
                if not isinstance(responsibilities, list):
                    raise ProfileDocumentError("경력 responsibilities 배열이 필요함")
                evidence = _text(value.get("responsibility_evidence"), "responsibility_evidence")
                if evidence in responsibilities:
                    raise ProfileDocumentError("경력 수행 근거가 현재 프로필에 이미 있음")
                responsibilities.append(evidence)
            elif operation == "append_achievement_evidence":
                career = career_index.get(record_id)
                if not isinstance(career, dict):
                    raise ProfileDocumentError("최종 변경안의 대상 경력이 현재 프로필에 없음")
                achievements = career.get("achievements")
                if not isinstance(achievements, list):
                    raise ProfileDocumentError("경력 achievements 배열이 필요함")
                achievement_id = "achievement-analysis-" + sha256(
                    f"{proposal_root['final_proposal_id']}|{change_id}".encode("utf-8")
                ).hexdigest()[:16]
                if any(
                    isinstance(item, Mapping) and item.get("achievement_id") == achievement_id
                    for item in achievements
                ):
                    raise ProfileDocumentError("최종 변경안의 성과 ID가 현재 프로필과 중복됨")
                problem = value.get("problem_evidence")
                action = value.get("action_evidence")
                result = value.get("result_evidence")
                title_source = result or action or problem or "확인된 성과 근거"
                title = _text(title_source, "achievement title")[:100]
                achievements.append(
                    {
                        "achievement_id": achievement_id,
                        "title": title,
                        "problem": problem,
                        "actions": [action] if action else [],
                        "result": result,
                        "evidence_level": "real_work",
                        "notes": "프로필 문서 분석 후 사용자 최종 승인",
                    }
                )
            elif operation == "append_skill_evidence":
                skill = skill_index.get(record_id)
                if not isinstance(skill, dict):
                    raise ProfileDocumentError("최종 변경안의 대상 기술이 현재 프로필에 없음")
                evidence_values = skill.get("evidence")
                if not isinstance(evidence_values, list):
                    raise ProfileDocumentError("기술 evidence 배열이 필요함")
                evidence = _text(value.get("usage_evidence"), "usage_evidence")
                if evidence in evidence_values:
                    raise ProfileDocumentError("기술 사용 근거가 현재 프로필에 이미 있음")
                evidence_values.append(evidence)
            elif operation == "add_skill_with_evidence":
                name = _text(value.get("technology_name"), "technology_name")
                normalized_name = normalize_skill_name(name)
                if record_id in skill_index or normalized_name in skill_names:
                    raise ProfileDocumentError("새 기술이 현재 프로필과 중복됨")
                new_skill = {
                    "skill_id": record_id,
                    "name": name,
                    "level": _text(value.get("proposed_level"), "proposed_level"),
                    "evidence": [_text(value.get("usage_evidence"), "usage_evidence")],
                    "notes": "프로필 문서 분석 후 사용자 최종 승인",
                }
                skills.append(new_skill)
                skill_index[record_id] = new_skill
                skill_names.add(normalized_name)
            else:
                raise ProfileDocumentError("최종 변경안에 지원하지 않는 적용 동작이 있음")
            applied_items.append({"change_id": change_id, "record_id": record_id, "operation": str(operation)})
        metadata = _mapping(updated_profile.get("metadata"), "metadata")
        if not isinstance(metadata, dict):
            raise ProfileDocumentError("metadata는 수정 가능한 객체여야 함")
        metadata["last_updated"] = applied_at.date().isoformat()
        output_hash = profile_content_sha256(updated_profile)

    final_id = str(proposal_root["final_proposal_id"])
    review_id = str(review_root["review_id"])
    application_id = "profile-analysis-application-" + sha256(
        "|".join((base_hash, final_id, review_id, PROFILE_ANALYSIS_APPLICATION_RULES_VERSION)).encode("utf-8")
    ).hexdigest()[:24]
    application = {
        "profile_analysis_application": {
            "application_id": application_id,
            "applied_at": applied_at.isoformat(timespec="microseconds"),
            "status": "applied_to_new_version" if updated_profile is not None else "rejected",
            "base_profile_id": proposal_root["base_profile_id"],
            "base_profile_content_sha256": base_hash,
            "source_final_proposal_id": final_id,
            "source_final_review_id": review_id,
            "output_profile_content_sha256": output_hash,
            "rules_version": PROFILE_ANALYSIS_APPLICATION_RULES_VERSION,
        },
        "summary": {
            "proposed_count": len(proposal["resolved_changes"]),
            "applied_count": len(applied_items),
        },
        "applied_items": applied_items,
        "metadata": {
            "schema_version": PROFILE_ANALYSIS_APPLICATION_SCHEMA_VERSION,
            "contains_personal_data": True,
            "contains_profile_content": False,
            "git_tracking_allowed": False,
            "profile_updated": updated_profile is not None,
        },
    }
    return application, updated_profile


def _read_json(path: Path, description: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProfileDocumentError(f"{description}을 읽을 수 없음") from error
    if not isinstance(value, dict):
        raise ProfileDocumentError(f"{description} 최상위 JSON은 객체여야 함")
    return value


def save_profile_analysis_application(
    application: Mapping[str, Any],
    updated_profile: Mapping[str, Any] | None,
    directory: str | Path,
) -> tuple[Path, bool]:
    root = _mapping(application.get("profile_analysis_application"), "application")
    metadata = _mapping(application.get("metadata"), "metadata")
    application_id = _text(root.get("application_id"), "application_id")
    if _APPLICATION_ID_PATTERN.fullmatch(application_id) is None:
        raise ProfileDocumentError("프로필 분석 적용 ID가 올바르지 않음")
    expected_profile = root.get("status") == "applied_to_new_version"
    if root.get("status") not in {"applied_to_new_version", "rejected"}:
        raise ProfileDocumentError("프로필 분석 적용 상태가 올바르지 않음")
    if metadata.get("schema_version") != PROFILE_ANALYSIS_APPLICATION_SCHEMA_VERSION:
        raise ProfileDocumentError("현재 버전의 프로필 분석 적용 기록이 아님")
    if metadata.get("profile_updated") is not expected_profile:
        raise ProfileDocumentError("프로필 분석 적용 상태와 갱신 표시가 다름")
    if (updated_profile is not None) is not expected_profile:
        raise ProfileDocumentError("프로필 분석 적용 상태와 새 프로필 파일 유무가 다름")
    if updated_profile is not None:
        if root.get("output_profile_content_sha256") != profile_content_sha256(updated_profile):
            raise ProfileDocumentError("새 프로필 지문이 적용 기록과 일치하지 않음")
    elif root.get("output_profile_content_sha256") is not None:
        raise ProfileDocumentError("거부된 적용 기록에는 새 프로필 지문이 없어야 함")
    if metadata.get("contains_profile_content") is not False or metadata.get("git_tracking_allowed") is not False:
        raise ProfileDocumentError("프로필 분석 적용 기록의 데이터 경계가 올바르지 않음")

    output_directory = Path(directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    target_directory = output_directory / application_id
    application_path = target_directory / "application.json"
    profile_path = target_directory / "profile.json"
    if target_directory.exists():
        existing = _read_json(application_path, "기존 프로필 분석 적용 기록")
        existing_root = dict(_mapping(existing.get("profile_analysis_application"), "application"))
        current_root = dict(root)
        existing_root.pop("applied_at", None)
        current_root.pop("applied_at", None)
        comparable_existing = dict(existing)
        comparable_current = dict(application)
        comparable_existing["profile_analysis_application"] = existing_root
        comparable_current["profile_analysis_application"] = current_root
        if comparable_existing != comparable_current:
            raise ProfileDocumentError("같은 적용 ID의 기존 기록이 일치하지 않음")
        if updated_profile is not None and _read_json(profile_path, "기존 새 프로필") != updated_profile:
            raise ProfileDocumentError("같은 적용 ID의 기존 새 프로필이 일치하지 않음")
        return application_path, False
    temporary_directory = Path(tempfile.mkdtemp(prefix=f".{application_id}.", dir=output_directory))
    try:
        (temporary_directory / "application.json").write_text(json.dumps(application, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        if updated_profile is not None:
            (temporary_directory / "profile.json").write_text(json.dumps(updated_profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        os.replace(temporary_directory, target_directory)
    except OSError as error:
        raise ProfileDocumentError("프로필 분석 적용 결과를 저장할 수 없음") from error
    finally:
        if temporary_directory.exists():
            shutil.rmtree(temporary_directory)
    return application_path, True
