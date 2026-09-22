# Profile Analysis Draft Schema

## 1. 목적

프로필 추출 후보를 LLM이 경력, 성과, 기술 사용 근거와 미확인 질문으로 분류한 결과를 사용자 검토 전 초안으로 표현한다.

이 초안은 사용자 사실의 확정값이 아니다. 기존 사용자 프로필을 변경하지 않으며 모든 사실 표현은 원본 후보 ID와 후보 문장 안의 원문 구간을 참조해야 한다.

## 2. 현재 범위

- 입력: `PROFILE_EXTRACTION_SCHEMA` 0.1의 `needs_review` 후보
- 출력 계약 버전: 0.1
- 저장 위치: Git에서 제외된 `private-data/profile-analysis-drafts/`
- 실제 외부 LLM 호출: OpenAI 어댑터와 공개 합성 입력 전용 Gemini 개발 경로 구현
- 실제 문서 외부 전송 동의: Slack 문서 스레드와 최소 요청 지문에 묶인 승인·거부 기록 구현
- Slack 표시: 최신 검증 초안의 항목 수 요약과 항목별 표시 구현
- 항목 승인·거부: 같은 사용자·채널·스레드의 자연어 답변 연결 구현
- 프로필 변경 제안: 최신 승인 항목의 비파괴 매핑 제안 구현

현재 구현은 합성 공급자 응답으로 계약과 검증 경계를 확인하고 실제 문서의 외부 전송 동의·거부를 기록한다. 동의된 실제 이력서 후보를 외부 API에 보내 분석 초안을 생성하는 단계는 아직 연결하지 않았다.

공급자 요청에는 계약 버전과 후보 ID, 프로필 영역, 후보 문장만 포함한다. 문서 ID, 원문 파일명, 줄 번호와 저장 경로는 포함하지 않는다. 외부 전송 공급자는 실행 시 명시적 승인값이 없으면 호출 전에 거부한다.

동의 기록은 추출 결과 ID, 최소 공급자 요청의 SHA-256 지문, 공급자·모델, 정확한 Slack 세션·사용자·스레드, 승인 또는 거부와 결정 시각만 포함한다. 후보 문장, 파일 내용과 Slack 메시지 원문은 복제하지 않는다. 같은 Slack 스레드의 허용 사용자가 해당 세션에 남긴 기록만 후속 외부 분석의 입력으로 사용할 수 있다.

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
      "analysis_source": {
        "provider": "synthetic",
        "model": "fixture-v1",
        "data_boundary": "local"
      },
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

### 5.1 안전한 조회와 최신 초안 선택

저장된 초안을 다시 읽을 때 다음 항목을 검증한다.

- 파일명의 초안 ID와 JSON 내부 초안 ID 일치
- 추출 ID, 계약 버전과 `needs_review` 상태
- 시간대가 포함된 분석 시각
- 공급자, 모델과 로컬·외부 데이터 경계
- 분석 배열과 요약 개수 일치
- 개인정보 포함, Git 제외, 공급자 검증 완료와 프로필 미반영 표시
- 추출 ID, 공급자 정보와 분석 내용으로 다시 계산한 초안 ID 지문

`select_latest_profile_analysis_draft`는 같은 추출 ID에 연결된 검증된 초안만 모아 분석 시각과 초안 ID 순으로 최신 항목을 선택한다. 다른 문서에서 만든 초안은 분석 시각이 더 늦어도 선택하지 않는다. 초안 디렉터리가 아직 없거나 같은 추출 ID의 초안이 없으면 `None`을 반환한다.

### 5.2 분석 항목 검토 기록

검증된 초안의 각 배열 항목은 초안 ID, 항목 종류와 1부터 시작하는 순번으로 참조한다. 허용 항목 종류는 다음과 같다.

- `career_evidence`
- `achievement_evidence`
- `technology_evidence`
- `unknowns`

사용자 결정은 `approve` 또는 `reject`다. 검토 기록은 분석 문장, 후보 문장과 후보 ID를 복제하지 않고 다음 참조만 저장한다.

    {
      "profile_analysis_review": {
        "review_id": "profile-analysis-review-example",
        "reviewed_at": "2026-09-21T12:00:00+00:00",
        "decision": "approve",
        "notes": null
      },
      "source": {
        "draft_id": "profile-analysis-draft-example",
        "extraction_id": "profile-text-extraction-example",
        "item_type": "career_evidence",
        "item_position": 1
      }
    }

저장 전에 초안 전체 지문, 항목 존재 여부, 검토 ID 지문, 시간대와 비공개 메타데이터를 다시 검증한다. 결과는 `private-data/profile-analysis-reviews/`에 불변 파일로 저장하며 개인 프로필을 변경하지 않는다.

### 5.3 승인 항목의 프로필 변경 제안

같은 초안 항목에 결정이 여러 개 있으면 검토 시각과 검토 ID 순으로 최신 결정만 사용한다. 최신 결정이 `approve`인 경력, 성과와 기술 근거만 `private-data/profile-analysis-update-proposals/`의 비공개 변경 제안으로 변환한다.

- 경력 근거: 기존 경력 항목을 자동 추정하지 않고 `needs_career_selection`으로 표시한다.
- 성과 근거: 어느 경력의 성과인지 자동 추정하지 않고 `needs_career_selection`으로 표시한다.
- 기존 기술과 이름이 정확히 일치하는 기술 근거: 기존 기술 ID에 근거 추가를 제안하되 숙련도는 변경하지 않는다.
- 새 기술 근거: 기술 추가 후보로 만들고 숙련도 확인 전까지 `needs_skill_level_confirmation`으로 표시한다.
- 추가 확인 질문: 프로필 사실이 아니므로 변경 제안에서 제외하고 개수만 기록한다.
- 기존 기술에 동일한 근거가 있으면 새 변경을 만들지 않고 중복 제외 개수로 기록한다.

변경 제안에는 기준 프로필 내용 지문, 출처 초안과 추출 ID, 사용한 최신 결정 스냅샷과 제안 항목을 저장한다. 후보 ID와 후보 원문은 복제하지 않는다. 제안 ID는 기준 프로필 지문, 출처와 제안 내용의 지문으로 검증하며 `profile_updated`는 `false`로 유지한다.

## 6. 다음 단계

저장된 추출 결과와 로컬 합성 응답으로 전체 경계를 확인할 수 있다.

    python scripts/build_profile_analysis_draft.py --extraction-id profile-text-extraction-example --response-file data/profile_analysis_response.example.json

이 명령은 네트워크를 사용하지 않으며 후보 문장을 콘솔에 출력하지 않는다. 출력에는 항목별 개수, 검토 상태와 비공개 저장 경로만 포함한다.

다음 구현 순서는 다음과 같다.

1. 무료 Gemini 합성 fixture로 승인 지문과 외부 공급자 호출 경계를 검증한다.
2. 실제 문서는 외부 전송 없이 기존 로컬 추출 결과로 검토 가능한 초안을 만드는 경로를 먼저 구현한다.
3. 유료 공급자를 선택할 때 데이터 처리·보존 조건을 다시 검토하고 기존 문서별 동의 지문을 호출 직전에 검증한다.
4. 활성 프로필에서 검색 계획을 다시 생성하고 공고 발견·분석 전체 흐름을 검증한다.
