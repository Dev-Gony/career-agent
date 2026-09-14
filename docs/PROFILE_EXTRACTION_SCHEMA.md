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

## 7. 현재 한계

- 제목 기반 분류이며 문장의 의미를 해석하지 않는다.
- 한 줄 안의 기술 여러 개를 개별 기술로 분리하지 않는다.
- 기간, 경력 연수, 숙련도와 성과를 구조화하지 않는다.
- 후보 승인·거부와 기존 프로필 병합 기능은 아직 없다.
- PDF, DOCX와 이미지 OCR 추출은 아직 없다.
- 외부 LLM을 호출하지 않는다.

다음 단계에서는 후보 한 건씩 승인 또는 거부하는 불변 검토 기록을 만들고, 승인된 후보만 프로필 갱신안에 포함한다.
