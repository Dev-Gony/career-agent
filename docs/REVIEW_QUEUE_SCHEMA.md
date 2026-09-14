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
2. `high`, `medium`, `review` 순서를 우선한다.
3. 같은 우선순위에서는 프로필 선호 지역 일치 여부를 먼저 비교한다.
4. 그 다음 고용 형태 일치 여부를 비교한다.
5. 완전 일치 표현이 없는 `review` 후보는 Agent 생성 검색 계획의 직무 표현을 단어 단위로 다시 비교한다.
6. 나머지 순서는 실제 시간대로 해석한 공고 갱신 시각의 최신순이다.
7. 기업 보드와 외부 공고 ID가 같은 항목은 하나만 유지한다.
8. 기본 큐 크기는 10건이며 최대 50건이다.

`review`를 포함하는 이유는 완전 일치 기반 발견 규칙이 놓친 관련 직무를 찾아 false negative, 즉 관련 공고 누락을 검토하기 위해서다.

## 4. 구조

    review_queue:
      queue_id: "greenhouse-review-queue-20260914T110354520473+0900"
      created_at: "2026-09-14T11:03:54.520473+09:00"
      source_discovery_executed_at: "2026-09-14T10:50:10+09:00"
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

## 5. 분석 상태

- `analyzed_current`: 공고 갱신 시각, 프로필 내용, 매칭 규칙과 분석 파이프라인 버전이 모두 같은 상세 분석이 있음
- `needs_analysis`: 현재 입력과 규칙에 맞는 상세 분석이 없음

프로필이나 규칙이 바뀌면 같은 공고의 과거 분석도 `needs_analysis`로 표시한다.

## 6. 사용자 검토 상태

새 큐의 사용자 검토 값은 자동으로 채우지 않는다.

- `status`: 기본값 `not_reviewed`
- `fit_assessment`: 사용자의 실제 적합도 판단, 초기값 `null`
- `recommendation_useful`: 추천 유용성 판단, 초기값 `null`
- `notes`: 사용자 메모, 초기값 `null`

사용자가 직접 확인하지 않은 결과를 `reviewed`로 기록하지 않는다.

## 7. 저장 및 개인정보

- 기본 저장 경로: `private-data/review-queues/`
- 각 실행은 시간대와 마이크로초가 포함된 새 파일로 저장한다.
- 이전 큐를 덮어쓰지 않는다.
- 사용자 프로필 원문과 채용공고 본문을 저장하지 않는다.
- 실제 검토 큐는 공개 저장소에 커밋하지 않는다.

## 8. 현재 제한

- 가장 최근 분석 실행에 포함된 목록 스냅샷을 사용하므로 먼저 일반 Agent를 실행해 현재 목록을 갱신해야 한다.
- 큐 생성 자체는 새 공고 상세 본문을 조회하지 않는다.
- 현재는 큐에서 미분석 후보를 자동으로 하나씩 상세 분석하는 단계가 연결되지 않았다.
- 사용자 검토 값을 안전하게 입력하는 명령은 아직 없다.
