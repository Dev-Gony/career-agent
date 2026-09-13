# Match Result Schema

## 1. 목적

이 문서는 사용자 프로파일과 채용공고를 비교한 결과를 일관된 형태로 저장하기 위한 첫 MVP 출력 구조를 정의한다.

결과는 단순한 적합도 점수가 아니라 다음 내용을 추적할 수 있어야 한다.

- 어떤 공고 요구사항을 평가했는가
- 어떤 사용자 증거를 사용했는가
- 확인된 사실과 Agent의 해석은 무엇인가
- 무엇이 부족하고 무엇이 정보 부족인가
- 왜 현재 지원 판단을 제안했는가

## 2. 설계 원칙

1. 필수 조건과 우대 조건의 결과를 분리한다.
2. 각 판정에 공고 근거와 사용자 증거를 함께 기록한다.
3. `gap`과 `unknown`을 분리한다.
4. 지원 가능 조건과 역량 적합도를 분리한다.
5. 적합도 백분율은 첫 MVP에서 사용하지 않는다.
6. 내부의 상세한 사고 과정은 저장하지 않고 사용자에게 필요한 판단 근거만 저장한다.
7. 동일한 입력을 다시 확인할 수 있도록 입력 식별자와 규칙 버전을 기록한다.

## 3. 최상위 구조

첫 결과 데이터는 다음 영역으로 나눈다.

    match_result
    |-- identity
    |-- inputs
    |-- summary
    |-- eligibility
    |-- required_matches
    |-- preferred_matches
    |-- responsibility_matches
    |-- strengths
    |-- gaps
    |-- unknowns
    |-- learning_recommendations
    |-- portfolio_recommendations
    |-- application_recommendation
    |-- analysis_notes
    `-- metadata

## 4. identity

분석 결과를 구분하기 위한 정보다.

예시:

    identity:
      analysis_id: "analysis-job-001-sample-user-001-v1"
      status: "completed"
      created_at: "2026-09-13T18:30:00+09:00"

권장 `status` 값:

- pending
- completed
- incomplete
- failed

입력 정보가 부족해 일부 판정을 내리지 못했더라도 분석 자체가 정상 종료됐다면 `completed`로 기록하고 해당 항목을 `unknown`으로 표시한다.

## 5. inputs

어떤 입력을 비교했는지 기록한다.

예시:

    inputs:
      profile_id: "sample-user-001"
      profile_schema_version: "0.1"
      posting_id: "job-001"
      posting_source_url: "https://example.com/jobs/ai-automation-engineer"
      posting_collected_at: "2026-09-13"

향후 실제 자동 수집을 구현하면 입력 파일의 해시 또는 공고의 `content_hash`를 추가한다.

## 6. summary

결과를 빠르게 확인하기 위한 집계다.

예시:

    summary:
      required:
        total: 3
        strong_match: 3
        match: 0
        partial: 0
        gap: 0
        unknown: 0
      preferred:
        total: 3
        strong_match: 1
        match: 0
        partial: 0
        gap: 0
        unknown: 2

이 집계는 원본 판정 배열에서 계산할 수 있어야 하며 수동으로 다른 값을 넣지 않는다.

## 7. eligibility

경력, 학력, 지역, 고용 형태, 필수 자격처럼 실제 지원 가능 여부에 영향을 주는 조건을 기록한다.

예시:

    eligibility:
      status: "eligible"
      conditions:
        - type: "experience"
          posting_value: "신입 또는 경력"
          user_value: "경력 있음"
          result: "met"
          reason: "최소 경력 연수 제한이 없고 사용자에게 실무 경력이 있음"

권장 `status` 값:

- eligible
- conditional
- ineligible
- unknown

조건별 `result` 값:

- met
- not_met
- needs_confirmation
- not_applicable

역량이 잘 맞더라도 확인된 필수 지원 조건을 충족하지 못하면 이를 별도로 표시한다.

## 8. 공통 요구사항 판정 구조

`required_matches`, `preferred_matches`, `responsibility_matches`의 각 항목은 같은 기본 구조를 사용한다.

예시:

    - requirement:
        source_section: "requirements"
        source_id: "requirement-python"
        type: "skill"
        name: "Python"
        evidence_text: "Python을 활용한 개발 경험"
      assessment:
        result: "strong_match"
        directness: "exact"
        confidence: "high"
        reason: "완료된 자동화 프로젝트에서 Python을 사용한 증거가 있음"
      user_evidence:
        - source_type: "project"
          source_name: "Tech News Automation"
          source_id: "project-tech-news"
          evidence_level: "project"
          detail: "Python으로 수집, 중복 방지, LLM 요약과 예약 실행을 구현"
      unknowns: []
      next_action: null

`source_id`는 입력 데이터에 정의된 안정적인 항목 ID를 사용한다. 배열 위치나 이름만으로 참조하지 않으며, 입력 순서가 바뀌어도 같은 항목을 계속 가리켜야 한다.

## 9. assessment

요구사항 판정 정보를 저장한다.

필드:

- `result`: strong_match, match, partial, gap, unknown
- `directness`: exact, equivalent, related, none
- `confidence`: high, medium, low
- `reason`: 사용자가 이해할 수 있는 짧은 판단 근거

`confidence`는 적합도 점수가 아니다. 입력 정보와 증거의 명확성을 나타낸다.

권장 기준:

- high: 공고 문구와 사용자 증거가 모두 명확함
- medium: 관련 증거가 있지만 범위 또는 요구 수준 해석이 필요함
- low: 공고나 사용자 정보가 부족해 판단이 불안정함

## 10. user_evidence

판정에 사용한 사용자 근거를 저장한다.

필드:

- `source_type`: career, achievement, project, skill, behavior, assessment, preference
- `source_name`: 사람이 확인할 수 있는 근거 이름
- `source_id`: 사용자 프로파일에 정의된 안정적인 항목 ID
- `evidence_level`: work, project, observed_behavior, basic, learning, exposure, none, supporting
- `detail`: 요구사항과 연결되는 구체적인 내용

검사 결과나 업무 선호만으로 기술 요구사항의 `strong_match`를 만들 수 없다.

## 11. strengths

지원 시 강조할 수 있는 강점을 저장한다.

예시:

    strengths:
      - title: "운영 가능한 자동화 프로젝트 경험"
        related_requirements:
          - "automation project"
          - "Python"
        evidence:
          - "Tech News Automation"
        reason: "수집부터 중복 방지, 예약 실행, 전달까지 전체 흐름을 구현함"

단순 성격 특성보다 공고 요구사항과 연결된 실제 증거를 우선한다.

## 12. gaps

확인된 부족 역량만 기록한다.

예시:

    gaps:
      - name: "필수 자격증"
        priority: "blocking"
        reason: "공고는 필수로 요구하지만 사용자 프로파일에서 미보유가 확인됨"
        recommended_action: "지원 전 자격 요건을 다시 확인"

권장 `priority` 값:

- blocking
- immediate
- parallel
- preferred_only
- low

정보가 없다는 이유만으로 `gaps`에 추가하지 않는다.

## 13. unknowns

추가 확인이 필요한 내용을 저장한다.

예시:

    unknowns:
      - subject: "Kubernetes 사용 경험"
        source: "preferred_qualifications"
        impact: "우대 조건 판정에만 영향"
        question: "Kubernetes를 사용해 애플리케이션을 배포한 경험이 있는가"

질문은 판단을 바꿀 가능성이 큰 항목부터 정렬한다.

## 14. learning_recommendations

확인된 부족 또는 중요한 부분 적합 항목에 대한 보완 행동을 저장한다.

예시:

    learning_recommendations:
      - topic: "Docker"
        priority: "preferred_only"
        based_on: "Docker 사용 경험 우대"
        action: "기존 Tech News Automation을 컨테이너로 실행"
        deliverable: "Dockerfile과 로컬 실행 문서"
        completion_evidence: "새 환경에서 동일한 실행 결과 확인"

기술명만 나열하지 않고 실행할 작업, 산출물, 완료 증거를 함께 기록한다.

## 15. portfolio_recommendations

기존 프로젝트 개선을 우선하는 추천을 저장한다.

예시:

    portfolio_recommendations:
      - target_project: "Tech News Automation"
        related_gap: "Docker 프로젝트 사용 경험 부족"
        change: "컨테이너 실행 환경 추가"
        reason: "새 프로젝트 없이 기존 자동화 프로젝트의 재현성과 배포 역량을 증명할 수 있음"
        expected_evidence: "Dockerfile, 실행 명령, 검증 로그"

새 프로젝트는 기존 프로젝트 확장으로 증명하기 어려운 경우에만 추천한다.

## 16. application_recommendation

최종 지원 판단과 핵심 근거를 저장한다.

예시:

    application_recommendation:
      decision: "적극 지원"
      confidence: "high"
      reasons:
        - "세 가지 필수 조건 모두 프로젝트 증거가 있음"
        - "확인된 지원 불가 조건이 없음"
      cautions:
        - "Docker와 AWS 경험은 추가 확인 필요"
      next_steps:
        - "실제 공고의 상세 업무와 기술 사용 비중 확인"

`decision` 값은 `docs/MATCHING_RULES.md`의 지원 판단 목록만 사용한다.

## 17. analysis_notes

사실, 해석, 미확인 내용을 분리한다.

예시:

    analysis_notes:
      facts:
        - "Python 개발 경험이 필수 조건으로 제시됨"
      interpretations:
        - "사용자의 자동화 프로젝트가 핵심 업무와 직접 연결될 가능성이 높음"
      unknowns:
        - "실제 AWS 사용 비중은 공고만으로 확인할 수 없음"

해석을 사실처럼 기록하지 않는다.

## 18. metadata

분석 재현에 필요한 정보를 기록한다.

예시:

    metadata:
      schema_version: "0.1"
      matching_rules_version: "0.1"
      analysis_mode: "mvp_rule_based"
      generated_by: "career-agent"
      human_review_status: "not_reviewed"

권장 `human_review_status` 값:

- not_reviewed
- reviewed
- corrected
- accepted

사용자가 직접 검토하지 않은 결과는 `reviewed` 또는 `accepted`로 기록하지 않는다.

## 19. 첫 MVP 필수 필드

첫 구현에서 반드시 생성해야 하는 필드는 다음과 같다.

- identity
- inputs
- summary
- eligibility
- required_matches
- preferred_matches
- strengths
- gaps
- unknowns
- application_recommendation
- metadata

`responsibility_matches`, 학습 추천과 포트폴리오 추천은 입력 정보가 충분할 때 생성하고, 없으면 빈 배열로 유지할 수 있다.

## 20. 완료 기준

다음 조건을 모두 만족하면 결과 스키마 정의가 구현에 사용할 수 있는 상태로 본다.

- 필수 조건과 우대 조건의 결과를 별도로 저장할 수 있다.
- 요구사항별 공고 근거와 사용자 증거를 추적할 수 있다.
- `gap`과 `unknown`을 별도로 집계할 수 있다.
- 역량 적합도와 지원 가능 조건을 별도로 저장할 수 있다.
- 최종 지원 판단의 이유와 주의사항을 확인할 수 있다.
- 사용자가 검토했는지 여부를 명확히 기록할 수 있다.

## 21. 다음 단계

1. `data/match_result.example.json`의 모든 참조가 실제 입력 ID와 연결되는지 검증한다.
2. 예제 결과가 `docs/MATCHING_RULES.md`와 일치하는지 수동 검토한다.
3. 예제 결과를 재현하는 최소 비교 기능의 입력과 출력 경계를 정의한다.
4. 경계가 확정된 뒤 최소 비교 기능을 구현한다.
