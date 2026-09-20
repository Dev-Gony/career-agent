# Profile Analysis Draft Schema

## 1. 목적

프로필 추출 후보를 LLM이 경력, 성과, 기술 사용 근거와 미확인 질문으로 분류한 결과를 사용자 검토 전 초안으로 표현한다.

이 초안은 사용자 사실의 확정값이 아니다. 기존 사용자 프로필을 변경하지 않으며 모든 사실 표현은 원본 후보 ID와 후보 문장 안의 원문 구간을 참조해야 한다.

## 2. 현재 범위

- 입력: `PROFILE_EXTRACTION_SCHEMA` 0.1의 `needs_review` 후보
- 출력 계약 버전: 0.1
- 저장 위치: Git에서 제외된 `private-data/profile-analysis-drafts/`
- 실제 외부 LLM 호출: 미구현
- Slack 표시 및 승인: 미구현

현재 구현은 합성 공급자 응답으로 계약과 검증 경계만 확인한다. 실제 이력서 후보를 외부 API에 전송하지 않는다.

## 3. 공급자 응답 계약

최상위 필드는 다음 네 배열로 제한한다.

- `career_evidence`
- `achievement_evidence`
- `technology_evidence`
- `unknowns`

추가 필드는 허용하지 않는다. 각 항목은 최대 50개, 한 항목의 후보 참조는 최대 10개다.

### 3.1 경력 근거

    {
      "role_or_context": "QA Engineer",
      "period_expression": "2022년",
      "responsibility_evidence": "API 테스트 자동화를 수행했습니다.",
      "candidate_ids": ["candidate-001"],
      "confidence": "high"
    }

역할, 기간과 책임은 문자열 또는 `null`이다. 문자열이면 참조한 후보 문장에 그대로 포함된 원문 구간이어야 하며 세 항목이 모두 `null`일 수 없다.

### 3.2 성과 근거

    {
      "problem_evidence": null,
      "action_evidence": "회귀 테스트 시간을",
      "result_evidence": "40% 단축했습니다.",
      "candidate_ids": ["candidate-002"],
      "confidence": "high"
    }

문제, 행동과 결과는 문자열 또는 `null`이다. 문자열이면 참조한 후보의 원문 구간이어야 하며 세 항목이 모두 `null`일 수 없다.

### 3.3 기술 사용 근거

    {
      "technology_name": "Python",
      "usage_evidence": "Python으로 테스트 데이터 검증 도구를 개발했습니다.",
      "proficiency_status": "unconfirmed",
      "candidate_ids": ["candidate-003"],
      "confidence": "high"
    }

기술명과 사용 근거는 참조한 후보 문장의 원문 구간이어야 한다. 기술 숙련도는 사용자 확인 전까지 `unconfirmed`로 고정한다.

### 3.4 미확인 질문

    {
      "question": "Python을 실제 업무에서 얼마나 자주 사용했나요?",
      "reason": "원문만으로 사용 빈도와 숙련도를 확정할 수 없습니다.",
      "candidate_ids": ["candidate-003"],
      "confidence": "medium"
    }

미확인 질문은 새로운 사실을 주장하지 않고 사용자에게 확인할 정보와 이유를 기록한다.

## 4. 로컬 검증

`validate_profile_analysis_response`는 다음 출력을 거부한다.

- 현재 추출 결과에 존재하지 않는 후보 ID 참조
- 참조 후보 문장에 없는 역할, 기간, 성과, 기술명 또는 사용 근거
- `unconfirmed`가 아닌 기술 숙련도
- 허용되지 않은 최상위 또는 항목 필드
- 중복 후보 참조와 허용 개수를 넘는 배열
- 후보가 사용자 프로필에 이미 적용됐다고 표시된 추출 결과

이 검증은 원문 구간의 존재를 확인할 뿐 해당 경력의 진실성을 확정하지 않는다. 사용자 승인이 별도로 필요하다.

## 5. 저장 결과

검증된 결과는 `profile-analysis-draft-<hash>.json`으로 저장한다.

    {
      "profile_analysis_draft": {
        "draft_id": "profile-analysis-draft-example",
        "source_extraction_id": "profile-text-extraction-example",
        "contract_version": "0.1",
        "status": "needs_review"
      },
      "analysis": {},
      "summary": {
        "career_evidence_count": 1,
        "achievement_evidence_count": 1,
        "technology_evidence_count": 1,
        "unknown_count": 1
      },
      "metadata": {
        "schema_version": "0.1",
        "contains_personal_data": true,
        "contains_candidate_text": true,
        "git_tracking_allowed": false,
        "provider_output_validated": true,
        "profile_updated": false
      }
    }

동일한 추출 결과와 동일한 분석 내용은 같은 ID를 사용한다. 기존 파일의 내용이 다르면 덮어쓰지 않고 오류로 처리한다.

## 6. 다음 단계

1. 공급자에 의존하지 않는 분석 인터페이스를 추가한다.
2. 합성 응답 공급자로 전체 호출 흐름을 확인한다.
3. 사용자 동의와 API Key가 준비된 뒤에만 OpenAI Responses API 구현을 추가한다.
4. Slack에서 초안을 보여주고 항목별 승인 또는 거부를 받는다.
