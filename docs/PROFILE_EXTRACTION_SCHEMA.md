# Profile Extraction Schema

## 1. 목적

저장된 사용자 문서에서 찾은 경력·프로젝트·기술·학력·희망 직무 문장을 기존 사용자 프로필과 분리된 검토 후보로 표현한다.

이 결과는 AI가 확정한 사용자 사실이 아니다. 모든 후보는 사용자가 확인하기 전까지 `needs_review` 상태이며 기존 `user_profile`을 변경하지 않는다.

## 2. 현재 입력 범위

- 비공개 문서 저장소에서 해시와 크기 검증이 끝난 문서
- UTF-8 `.txt` 또는 `.md`
- 추출 규칙 버전 `0.1`

PDF와 DOCX는 원본 저장만 지원하며 현재 텍스트 후보 추출에서는 거부한다.

## 3. 추출 규칙

다음과 같이 인식된 섹션 제목 아래의 문장만 후보로 만든다.

| 문서 제목 예 | 프로필 후보 영역 |
| --- | --- |
| 경력, 경력사항, Experience | `career_history` |
| 프로젝트, Projects | `projects` |
| 기술, 기술 스택, Skills | `skills` |
| 학력, 교육, Education | `education` |
| 희망 직무, 지원 분야, Target Role | `target_roles` |
| 업무 선호, 근무 선호, Work Preferences | `work_preferences` |

제목 없이 등장한 문장은 사실로 추정하지 않고 개수만 기록한다. Markdown의 인식되지 않은 새 제목은 이전 섹션을 종료한다.

## 4. 후보 구조

    profile_extraction:
      extraction_id: "profile-text-extraction-example"
      extracted_at: "2026-09-14T15:00:00+09:00"
      method: "heading_based_text"
      rules_version: "0.1"
      status: "needs_review"

    source_document:
      document_id: "profile-document-resume-example"
      document_kind: "resume"
      document_format: "markdown"
      content_sha256: "원본 전체 SHA-256"

    candidates:
      - candidate_id: "candidate-001"
        profile_section: "skills"
        text: "Python"
        status: "needs_review"
        source_evidence:
          document_id: "profile-document-resume-example"
          line_start: 10
          line_end: 10

    metadata:
      schema_version: "0.1"
      contains_personal_data: true
      git_tracking_allowed: false
      profile_updated: false

후보는 원문 전체가 아니라 해당 섹션의 한 줄과 줄 번호만 보존한다. 결과 파일은 개인정보를 포함할 수 있으므로 `private-data/profile-extractions/`에만 저장한다.

## 5. 민감정보 제외

현재 다음 형태가 있는 줄은 후보로 저장하지 않고 제외 개수만 기록한다.

- 이메일 주소
- 국내 전화번호 형태
- 주민등록번호 형태
- 이메일, 전화, 연락처, 주소로 시작하는 레이블
- 연락처 또는 주소 섹션 아래의 문장

이 규칙은 완전한 개인정보 탐지기가 아니다. 상세 주소의 모든 표현이나 문맥상 개인정보를 보장해서 찾지 못하므로 결과 파일은 계속 비공개 데이터로 취급한다.

## 6. 실행

먼저 문서를 가져온다.

    python scripts/import_profile_document.py --file data/profile_document.example.md --kind resume

출력된 문서 ID를 사용해 후보를 추출한다.

    python scripts/extract_profile_text.py --document-id profile-document-resume-example

동일 문서와 동일 규칙 버전의 추출은 기존 결과를 재사용한다. 콘솔에는 후보 수와 영역별 수만 표시하고 후보 문장 자체는 출력하지 않는다.

## 7. 후보 승인 또는 거부

`scripts/review_profile_candidate.py`는 추출 후보 한 건에 사용자가 명시한 결정을 기록한다.

    python scripts/review_profile_candidate.py --extraction-id profile-text-extraction-example --candidate-id candidate-001 --decision approve

허용 결정은 다음 두 가지다.

- `approve`: 프로필 갱신안에 포함할 수 있도록 승인
- `reject`: 프로필 갱신안에서 제외하도록 거부

결과는 `private-data/profile-candidate-reviews/`에 불변 JSON으로 저장한다.

    candidate_review:
      review_id: "profile-candidate-review-example"
      reviewed_at: "2026-09-14T16:00:00+09:00"
      decision: "approve"
      notes: null

    source:
      extraction_id: "profile-text-extraction-example"
      candidate_id: "candidate-001"
      profile_section: "skills"
      document_id: "profile-document-resume-example"
      line_start: 10
      line_end: 10

    metadata:
      schema_version: "0.1"
      contains_personal_data: true
      contains_candidate_text: false
      git_tracking_allowed: false
      profile_updated: false

검토 기록에는 후보 문장을 복제하지 않는다. 동일 후보를 다시 판단해도 이전 기록을 덮어쓰지 않으며 다음 프로필 갱신안 단계에서 가장 최근의 명시적 결정을 선택한다.

## 8. 프로필 갱신안

`scripts/build_profile_update_proposal.py`는 추출 결과에 연결된 검토 기록을 모아 기존 프로필과 분리된 갱신안을 만든다.

    python scripts/build_profile_update_proposal.py --extraction-id profile-text-extraction-example

후보별로 시간대가 포함된 `reviewed_at`이 가장 늦은 결정을 사용한다. 최신 결정이 `approve`인 후보만 `proposed_additions`에 포함하고, `reject`와 미검토 후보는 개수만 요약한다.

    profile_update_proposal:
      proposal_id: "profile-update-proposal-example"
      status: "needs_mapping"
      base_profile_id: "sample-user-001"
      base_profile_content_sha256: "기준 프로필 전체 SHA-256"
      source_extraction_id: "profile-text-extraction-example"

    proposed_additions:
      - proposal_item_id: "proposal-item-001"
        profile_section: "skills"
        candidate_text: "Python"
        mapping_status: "needs_mapping"
        source_evidence:
          extraction_id: "profile-text-extraction-example"
          candidate_id: "candidate-001"
          document_id: "profile-document-resume-example"
          line_start: 10
          line_end: 10
        approval:
          review_id: "profile-candidate-review-example"
          reviewed_at: "2026-09-14T16:00:00+09:00"
          decision: "approve"

    metadata:
      schema_version: "0.1"
      git_tracking_allowed: false
      profile_updated: false

기준 프로필의 정규화된 JSON 전체에 SHA-256을 계산해 기록한다. 이후 실제 반영 단계에서는 이 지문이 달라졌으면 오래된 갱신안을 거부할 수 있다. 승인 문장은 아직 `USER_PROFILE_SCHEMA`의 중첩 객체로 임의 변환하지 않고 `needs_mapping`으로 남긴다.

결과는 `private-data/profile-update-proposals/`에 저장한다. 같은 기준 프로필, 추출 결과와 최신 검토 집합은 같은 제안 ID를 사용하며 기존 내용이 동일할 때만 재사용한다. 이 명령은 기존 사용자 프로필 파일을 수정하지 않는다.

## 9. 기술 후보 매핑안

승인 후보 중 `profile_section`이 `skills`인 항목만 기존 프로필의 기술 목록과 비교한다.

    python scripts/build_profile_skill_mapping.py --proposal-id profile-update-proposal-example

기술명 비교는 Unicode NFKC 정규화, 대소문자와 연속 공백 정리만 적용한다. 별칭이나 유사어를 같은 기술로 추정하지 않는다.

매핑 상태는 다음과 같다.

- `duplicate_existing`: 정규화한 이름이 기존 기술과 정확히 같아 기존 `skill_id`를 연결함
- `needs_details`: 새 단일 기술명으로 보이지만 `level`과 `evidence`가 없어 추가 확인이 필요함
- `needs_separation`: 쉼표, 세미콜론, 세로줄 또는 가운뎃점으로 여러 기술이 섞였을 수 있어 개별 기술명 분리가 필요함

    profile_skill_mapping:
      mapping_id: "profile-skill-mapping-example"
      status: "needs_confirmation"
      base_profile_id: "sample-user-001"
      base_profile_content_sha256: "기준 프로필 전체 SHA-256"
      source_update_proposal_id: "profile-update-proposal-example"
      rules_version: "0.1"

    skill_mappings:
      - mapping_item_id: "skill-mapping-item-001"
        candidate_text: "FastAPI"
        candidate_name: "FastAPI"
        mapping_status: "needs_details"
        existing_skill: null
        missing_fields:
          - "level"
          - "evidence"
        profile_change_ready: false

결과는 `private-data/profile-skill-mappings/`에 저장한다. 기존 기술 중복이어도 자동으로 덮어쓰지 않으며, 새 기술 후보에도 숙련도와 사용 증거를 임의로 채우지 않는다. 모든 항목의 `profile_change_ready`와 전체 `profile_updated`는 계속 `false`다.

## 10. 새 기술 세부정보 확인

`needs_details` 기술 후보 한 건에 사용자가 명시적으로 확인한 숙련도와 사용 증거를 기록한다.

    python scripts/confirm_profile_skill.py --mapping-id profile-skill-mapping-example --mapping-item-id skill-mapping-item-001 --level project --evidence "Tech News Automation에서 사용"

증거가 여러 개면 `--evidence`를 반복한다.

허용 숙련도는 `none`, `exposure`, `learning`, `basic`, `project`, `work`다. 사용 증거는 최소 1개, 최대 10개이며 각 항목은 300자 이하로 제한한다. 선택 메모는 1000자 이하로 제한한다.

    profile_skill_confirmation:
      confirmation_id: "profile-skill-confirmation-example"
      confirmed_at: "2026-09-14T19:00:00+09:00"
      confirmation_source: "explicit_user_input"
      level: "project"
      evidence:
        - "Tech News Automation에서 사용"
      notes: null

    source:
      mapping_id: "profile-skill-mapping-example"
      mapping_item_id: "skill-mapping-item-001"
      source_update_proposal_id: "profile-update-proposal-example"
      candidate_id: "candidate-001"
      document_id: "profile-document-resume-example"
      line_start: 10
      line_end: 10

    metadata:
      schema_version: "0.1"
      contains_personal_data: true
      contains_candidate_text: false
      git_tracking_allowed: false
      profile_updated: false

기록에는 후보 기술명을 자동 복제하지 않고 매핑 항목과 원문 근거를 참조한다. 결과는 `private-data/profile-skill-confirmations/`에 불변 파일로 저장한다. `duplicate_existing`과 `needs_separation` 항목은 이 명령으로 확인할 수 없다.

## 11. 현재 한계

- 제목 기반 분류이며 문장의 의미를 해석하지 않는다.
- 한 줄 안의 기술 여러 개를 개별 기술로 분리하지 않는다.
- 기간, 경력 연수, 숙련도와 성과를 구조화하지 않는다.
- `needs_details` 기술 후보의 숙련도와 증거를 확인할 수 있지만 여러 확인 기록 중 최신 판단을 선택하거나 완성된 기술 추가안을 만들지 않는다.
- 기술 후보를 실제 프로필에 적용하지 않는다.
- 목표 직무, 경력, 프로젝트와 다른 프로필 영역은 아직 타입 매핑하지 않는다.
- PDF, DOCX와 이미지 OCR 추출은 아직 없다.
- 외부 LLM을 호출하지 않는다.

다음 단계에서는 기술 후보별 가장 최근 세부정보 확인을 선택하고, 확인이 끝난 후보만 완성된 기술 추가안으로 만들되 실제 프로필 적용은 분리한다.
