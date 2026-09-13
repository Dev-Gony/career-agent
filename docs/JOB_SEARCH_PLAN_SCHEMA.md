# Job Search Plan Schema

## 1. 목적

사용자에게 검색 키워드나 제외 조건을 다시 입력받지 않고, 구조화된 사용자 프로필에서 채용공고 발견 계획을 생성하기 위한 입력과 기대 출력 구조를 정의한다.

이 계획은 채용공고의 최종 적합도 판정이 아니다. 어떤 공고를 넓게 발견하고 어떤 후보부터 상세 내용을 확인할지 결정하는 검색 전략이다.

## 2. 설계 원칙

1. 목표 직무, 경력, 프로젝트, 기술과 선호에서 검색 계획을 생성한다.
2. 생성된 검색어와 우선순위의 프로필 근거를 추적할 수 있어야 한다.
3. 단순 키워드 불일치만으로 후보를 제거하지 않는다.
4. 낮은 선호는 기본적으로 강제 제외가 아니라 순위 조정에 사용한다.
5. 프로필에 없는 연차나 재택 선호를 질문의 기본값으로 만들거나 추정하지 않는다.
6. 공고 상세 정보가 부족하면 최종 적합도 대신 발견 우선순위만 만든다.

## 3. 최상위 구조

    job_search_plan
    |-- identity
    |-- source_profile
    |-- role_axes
    |-- capability_signals
    |-- preference_signals
    |-- objective_preferences
    |-- unknown_constraints
    |-- discovery_sources
    |-- ranking_policy
    `-- metadata

## 4. identity

검색 계획 자체의 식별 정보를 저장한다.

예시:

    identity:
      plan_id: "search-plan-sample-user-001-v1"
      profile_id: "sample-user-001"
      version: 1
      generated_at: "2026-09-13T10:00:00+09:00"

같은 프로필에서 규칙이나 근거가 바뀌면 `version`을 올린다.

## 5. source_profile

검색 계획이 사용한 프로필 영역을 기록한다.

예시:

    source_profile:
      target_role_ids:
        - "role-ai-automation"
        - "role-ai-solutions"
        - "role-enterprise-solution"
        - "role-cloud-finops"
        - "role-data-analytics-automation"
      evidence_ids:
        - "career-001"
        - "achievement-001"
        - "project-tech-news"
        - "project-career-agent"
        - "skill-python"
        - "skill-rest-api"
        - "skill-llm-api"
        - "skill-github-actions"
      preference_fields:
        - "basic.location_preference"
        - "basic.employment_type_preference"
        - "career_goals.avoid_if_possible"
        - "work_preferences.less_preferred"

ID를 가진 경력, 프로젝트와 기술은 `evidence_ids`로 참조한다. 배열 항목 ID가 아직 없는 선호 영역은 배열 위치가 아니라 스키마 필드 이름과 실제 값으로 근거를 남긴다.

## 6. role_axes

목표 직무를 실제 공고에서 사용될 수 있는 여러 표현으로 확장한다.

예시:

    role_axes:
      - target_role_id: "role-ai-automation"
        priority: 1
        canonical_role: "AI Automation / Workflow Engineer"
        discovery_terms:
          - "AI 자동화"
          - "업무 자동화"
          - "워크플로 자동화"
          - "Automation Engineer"
        supporting_terms:
          - "Python"
          - "API"
          - "LLM"
          - "GitHub Actions"
        rationale: "프로젝트에서 데이터 수집, API 연동, LLM 요약과 예약 실행을 구현한 증거가 있음"

`discovery_terms`는 공고를 넓게 찾기 위한 직무 및 문제 표현이다. `supporting_terms`는 같은 제목의 후보를 정렬할 때 사용하는 역량 표현이다.

검색어는 사용자가 직접 관리하는 고정 목록이 아니다. 프로필의 목표 직무와 실제 공고 표현을 연결하기 위한 Agent 생성 결과이며 근거와 함께 검토할 수 있어야 한다.

## 7. capability_signals

경력, 프로젝트와 기술에서 후보 우선순위를 높일 수 있는 역량 신호를 만든다.

예시:

    capability_signals:
      - signal: "업무 자동화 구현"
        importance: "high"
        evidence_ids:
          - "project-tech-news"
          - "project-career-agent"
      - signal: "REST API 연동"
        importance: "high"
        evidence_ids:
          - "skill-rest-api"
          - "project-tech-news"

권장 `importance` 값:

- high
- medium
- supporting

설치 또는 화면 확인만 한 `exposure` 수준의 기술은 긍정 역량 신호로 만들지 않는다. 따라서 Docker와 AWS는 현재 검색 우선순위를 높이는 근거가 아니다.

## 8. preference_signals

일하는 방식의 선호와 낮은 선호를 후보 순위에 반영한다.

예시:

    preference_signals:
      positive:
        - signal: "문제가 명확하고 결과를 직접 확인할 수 있음"
          source_field: "work_preferences.preferred"
      rank_down:
        - signal: "반복 수작업 중심"
          source_field: "career_goals.avoid_if_possible"
          action: "rank_down_only"

공고 제목만으로 실제 업무 방식을 판단하기 어려우므로 `rank_down`은 상세 업무 문구가 확보됐을 때 적용한다.

## 9. objective_preferences

프로필에 명시된 지역과 고용형태 조건을 저장한다.

예시:

    objective_preferences:
      locations:
        values:
          - "수도권"
        normalized_values:
          - "서울"
          - "경기"
          - "인천"
        handling: "soft_preference"
        unknown_policy: "keep"
      employment_types:
        values:
          - "정규직"
        handling: "soft_preference"
        unknown_policy: "keep"

현재 단계에서는 선호 조건을 절대 지원 자격으로 해석하지 않는다. 불명확한 후보는 제거하지 않고 `unknown`으로 유지한다.

## 10. unknown_constraints

프로필에서 확인할 수 없거나 공개 예제에서 비식별 처리된 조건을 기록한다.

예시:

    unknown_constraints:
      - field: "career_years"
        reason: "공개 예제에 경력 기간이 비공개로 처리됨"
        action: "do_not_filter"
      - field: "remote_preference"
        reason: "프로필에 확정된 선호가 없음"
        action: "ignore_for_discovery"

정보가 없다는 이유만으로 사용자에게 즉시 추가 입력을 요구하지 않는다. 해당 정보가 실제 결정을 막는 단계가 되었을 때만 질문한다.

## 11. discovery_sources

검색 계획을 적용할 공급자와 사용 범위를 기록한다.

예시:

    discovery_sources:
      - provider: "incruit"
        source_kind: "rss"
        status: "first_candidate"
        usage: "broad_discovery_and_metadata_ranking"
        detail_strategy: "official_or_employer_source_only"

권장 `status` 값:

- first_candidate
- planned
- approval_required
- policy_review_required
- disabled

## 12. ranking_policy

발견 후보의 우선순위를 정하는 원칙을 저장한다.

예시:

    ranking_policy:
      retrieval_mode: "broad_then_rank"
      hard_exclusions:
        - "이미 본 동일 provider/external_id"
      rank_up_order:
        - "우선순위가 높은 목표 직무 축과 관련됨"
        - "실제 프로젝트로 증명된 역량 신호가 있음"
        - "수도권 또는 정규직 선호와 일치함"
      rank_down_order:
        - "낮은 선호 업무 방식이 상세 공고에 명시됨"
        - "수도권 밖 또는 비정규 고용형태로 명시됨"
      keep_when_unknown:
        - "지역"
        - "고용형태"
        - "경력 연차"
        - "재택 여부"

경력 연차와 재택 여부는 현재 프로필에서 확정되지 않았으므로 강제 필터로 쓰지 않는다.

## 13. metadata

예시:

    metadata:
      schema_version: "1.0"
      generated_by: "profile_derived_rule"
      requires_manual_keywords: false
      requires_manual_exclusions: false
      requires_remote_preference: false
      is_example: true

## 14. 완료 기준

- 사용자가 별도의 포함 및 제외 키워드를 작성하지 않아도 검색 계획이 생성된다.
- 모든 직무 축이 사용자 프로필의 목표 직무 ID를 참조한다.
- 중요한 역량 신호가 경력, 프로젝트 또는 기술 ID를 참조한다.
- 낮은 선호가 제목 기반 강제 제외로 오용되지 않는다.
- 지역과 고용형태는 프로필에 명시된 값만 사용한다.
- 프로필에 없는 연차와 재택 선호는 추정하지 않는다.
- 후보 발견 우선순위와 최종 직무 적합도가 구분된다.

## 15. 우선순위 기대 사례

`data/job_discovery_ranking_cases.example.json`에서 다음 네 상황의 기대 결과를 정의한다.

1. 최우선 목표 직무가 제목에 직접 나타나는 후보는 `high`다.
2. 솔루션 구축처럼 관련성은 있지만 AI 및 자동화 비중이 불명확한 후보는 `medium`이다.
3. 조건부 데이터 분석 직무는 실제 행동 연결 여부를 확인하기 전까지 `review`다.
4. 후순위 직무이면서 지역과 고용형태 선호가 모두 다른 후보는 `low`다.

네 경우 모두 상세 업무와 자격 요건이 없으므로 `match_ready`는 `false`다. 발견 우선순위만으로 `strong_match`, `gap` 또는 지원 판단을 생성하지 않는다.
