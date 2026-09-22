"""Expose sourced draft evidence without promoting it to verified competence."""

from copy import deepcopy
from typing import Any


def _candidate_ids(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(
        isinstance(item, str) and item.strip() for item in value
    )


def build_document_evidence(
    profile_document: dict[str, Any], matches: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Keep career context separate from exact, requirement-linked skill evidence."""
    metadata = profile_document.get("metadata", {})
    profile = profile_document["profile"]
    draft = profile.get("provisional_evidence", {})
    if not isinstance(metadata, dict) or not isinstance(draft, dict):
        return None
    draft_id = draft.get("source_draft_id")
    if (
        metadata.get("data_type") != "provisional_search_profile"
        or metadata.get("status") != "provisional_search_only"
        or draft.get("status") != "unconfirmed"
        or not isinstance(draft_id, str)
        or not draft_id.strip()
    ):
        return None

    career_context = []
    for item in draft.get("career_evidence", []):
        if not isinstance(item, dict) or not _candidate_ids(item.get("candidate_ids")):
            continue
        if not all(isinstance(item.get(key), str) and item[key].strip()
                   for key in ("role_or_context", "responsibility_evidence")):
            continue
        career_context.append({
            "role_or_context": item["role_or_context"],
            "period_expression": item.get("period_expression"),
            "detail": item["responsibility_evidence"],
            "candidate_ids": deepcopy(item["candidate_ids"]),
        })

    skills = {}
    for skill in profile.get("skills", []):
        if not isinstance(skill, dict):
            continue
        provenance = skill.get("provenance", {})
        if (skill.get("level") == "unconfirmed"
                and skill.get("verification_status") == "unconfirmed"
                and isinstance(provenance, dict)
                and provenance.get("source_draft_id") == draft_id
                and _candidate_ids(provenance.get("candidate_ids"))):
            skills[skill["skill_id"]] = skill

    requirement_links = []
    for match in matches:
        evidence = []
        for item in match.get("user_evidence", []):
            skill = skills.get(item.get("source_id"))
            if (skill is None or item.get("source_type") != "skill"
                    or item.get("evidence_level") != "unconfirmed"
                    or item.get("detail") not in skill.get("evidence", [])):
                continue
            evidence.append({
                **deepcopy(item),
                "candidate_ids": deepcopy(skill["provenance"]["candidate_ids"]),
            })
        if not evidence:
            continue
        requirement = match["requirement"]
        requirement_links.append({
            "source_section": requirement["source_section"],
            "source_id": requirement["source_id"],
            "name": requirement["name"],
            "posting_evidence": requirement["evidence_text"],
            "user_evidence": evidence,
            "verification_status": "unconfirmed",
        })

    return {
        "status": "unconfirmed",
        "source_draft_id": draft_id,
        "career_context": career_context,
        "requirement_links": requirement_links,
    }
