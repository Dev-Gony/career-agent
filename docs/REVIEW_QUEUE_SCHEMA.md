# Greenhouse Review Queue Schema

## 1. 목적

실제 공고 10건의 상세 분석과 사용자 검토를 한꺼번에 실행하지 않고, 현재 Greenhouse 목록에서 검토할 후보를 먼저 자동 정렬하는 로컬 스냅샷 구조다.

이 큐는 공고 본문을 포함하지 않는다. 제목, 회사, 지역, 공식 URL, 프로필 관련성 근거와 최신 분석 여부만 저장한다.

## 2. 입력

- 가장 최근 Agent 분석 파일에 저장된 Greenhouse `current_records`
- 현재 사용자 프로필의 내용 지문
- Agent가 프로필에서 생성한 `job_search_plan`
- 같은 로컬 분석 폴더의 이전 상세 분석 결과

사용자가 직무 키워드나 공고 ID를 다시 입력하지 않는다.

## 3. 선택 규칙

1. `high`, `medium`, `review` 후보만 사용하고 `low`는 제외한다.
2. 지역 또는 고용 형태가 명시적으로 불일치하는 후보를 일치·미확인 후보 뒤로 보낸다.
3. 남은 후보는 `high`, `medium`, `review` 순서를 우선한다.
4. 같은 우선순위에서는 프로필 선호 지역 일치 여부를 먼저 비교한다.
5. 그 다음 고용 형태 일치 여부를 비교한다.
6. 완전 일치 표현이 없는 `review` 후보는 Agent 생성 검색 계획의 직무 표현을 단어 단위로 다시 비교한다.
7. 나머지 순서는 실제 시간대로 해석한 공고 갱신 시각의 최신순이다.
8. 기업 보드와 외부 공고 ID가 같은 항목은 하나만 유지한다.
9. 기본 큐 크기는 10건이며 최대 50건이다.

`review`를 포함하는 이유는 완전 일치 기반 발견 규칙이 놓친 관련 직무를 찾아 false negative, 즉 관련 공고 누락을 검토하기 위해서다.

## 4. 구조

    review_queue:
      queue_id: "greenhouse-review-queue-20260914T110354520473+0900"
      created_at: "2026-09-14T11:03:54.520473+09:00"
      source_discovery_executed_at: "2026-09-14T10:50:10+09:00"
      source_run_filename: "analysis-greenhouse-example.json"
      limit: 10

    summary:
      eligible_current_candidates: 56
      selected_candidates: 10
      priorities:
        high: 1
        medium: 1
        review: 8
      analysis_statuses:
        analyzed_current: 1
        needs_analysis: 9

    items:
      - position: 1
        candidate_key: "greenhouse:sendbird:8395379002"
        board_token: "sendbird"
        external_job_id: "8395379002"
        company: "Sendbird"
        title: "Software Engineer, AI Agent"
        location: "Seoul, South Korea"
        priority: "high"
        ranking_reason: "프로필에서 생성한 최우선 목표 직무 표현과 일치"
        location_assessment: "match"
        employment_assessment: "unknown"
        broad_role_signals:
          - "ai"
          - "agent"
          - "engineer"
        source_url: "https://example.invalid"
        source_updated_at: "2026-09-10T10:00:00+09:00"
        analysis_status: "analyzed_current"
        analysis_id: "analysis-example"
        human_review:
          status: "not_reviewed"
          fit_assessment: null
          recommendation_useful: null
          notes: null

    metadata:
      schema_version: "0.2"
      profile_content_sha256: "프로필 원문을 복제하지 않는 비교용 SHA-256"

## 5. 분석 상태

- `analyzed_current`: 공고 갱신 시각, 프로필 내용, 매칭 규칙과 분석 파이프라인 버전이 모두 같은 상세 분석이 있음
- `needs_analysis`: 현재 입력과 규칙에 맞는 상세 분석이 없음

프로필이나 규칙이 바뀌면 같은 공고의 과거 분석도 `needs_analysis`로 표시한다.

## 6. 다음 후보 1건 상세 분석

`scripts/analyze_next_greenhouse_review.py`는 최신 큐에서 다음 조건을 만족하는 첫 항목만 선택한다.

- `analysis_status`가 `needs_analysis`
- `location_assessment`가 `mismatch`가 아님
- `employment_assessment`가 `mismatch`가 아님
- 큐의 프로필 지문, 매칭 규칙과 분석 파이프라인 버전이 현재 입력과 같음

공식 Greenhouse 상세 API 요청은 실행당 최대 1건이다. 결과는 다음 세 위치에 새 파일로 저장한다.

- `private-data/agent-runs/`: 상세 분석 전체와 원본 큐 참조
- `private-data/execution-runs/`: 상세 본문 없는 최소 실행 이력
- `private-data/review-queues/`: 분석 ID가 연결된 후속 큐 스냅샷

원본 큐는 덮어쓰지 않으며 사용자 검토 상태도 자동 변경하지 않는다.

## 7. 사용자 검토 상태

새 큐의 사용자 검토 값은 자동으로 채우지 않는다.

- `status`: 기본값 `not_reviewed`
- `fit_assessment`: 사용자의 실제 적합도 판단, 초기값 `null`
- `recommendation_useful`: 추천 유용성 판단, 초기값 `null`
- `notes`: 사용자 메모, 초기값 `null`

사용자가 직접 확인하지 않은 결과를 `reviewed`로 기록하지 않는다.

`scripts/record_greenhouse_review.py`는 최신 큐에서 `analyzed_current`인 공고 한 건에만 사용자 판단을 기록한다. 입력 값은 다음과 같다.

- `fit_assessment`: `fit`, `hold`, `not_fit` 중 하나
- `recommendation_useful`: `yes`, `no`, `unknown` 중 하나
- `notes`: 선택 입력이며 최대 1000자

결과는 `private-data/human-reviews/`에 원본 큐와 별도인 불변 JSON으로 저장한다. 레코드는 공고 식별자, 회사, 제목, 공식 URL, 분석 ID와 사용자 입력만 포함하며 프로필 원문이나 공고 본문을 복제하지 않는다. 이 저장 함수는 향후 Slack 메시지 또는 버튼이 호출할 수 있는 내부 경계다.

## 8. 저장 및 개인정보

- 검토 큐 기본 저장 경로: `private-data/review-queues/`
- 사용자 판단 기본 저장 경로: `private-data/human-reviews/`
- 각 실행은 시간대와 마이크로초가 포함된 새 파일로 저장한다.
- 이전 큐를 덮어쓰지 않는다.
- 사용자 프로필 원문과 채용공고 본문을 저장하지 않는다.
- 실제 검토 큐는 공개 저장소에 커밋하지 않는다.

## 9. 현재 제한

- 가장 최근 분석 실행에 포함된 목록 스냅샷을 사용하므로 먼저 일반 Agent를 실행해 현재 목록을 갱신해야 한다.
- 큐 생성 자체는 새 공고 상세 본문을 조회하지 않는다.
- 다음 후보 분석 명령은 필수 조건 또는 주요 업무가 0개로 추출되면 경고한다. 알려진 Moloco 직급 그룹 형식은 첫 번째 직급만 구조화하지만 새로운 형식을 자동으로 추론해 교정하지 않는다.
- 별도 저장된 사용자 판단을 새 큐 생성과 후보 정렬에 다시 병합하지 않는다.
