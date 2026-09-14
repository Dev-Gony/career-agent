# Job Discovery Schema

## 1. 목적

공식 RSS, 공식 API 또는 검색엔진 API에서 발견한 채용공고 후보를 상세 분석 전 단계에서 일관되게 저장한다.

이 구조는 `JOB_POSTING_SCHEMA`를 대체하지 않는다. 상세 정보가 확보되지 않은 후보를 완전한 채용공고처럼 취급하지 않기 위한 별도 경계다.

## 2. 설계 원칙

1. 공고 발견과 상세 분석 가능 여부를 분리한다.
2. 공급자와 외부 공고 ID를 함께 저장해 중복을 판단한다.
3. 원문 전문 대신 발견과 1차 선별에 필요한 최소 메타데이터만 저장한다.
4. 확인되지 않은 필드는 추정하지 않고 `null` 또는 `unknowns`로 남긴다.
5. 접근 경로와 확인 시점을 기록해 정책 재검토가 가능하게 한다.

## 3. 최상위 구조

    job_discovery
    |-- identity
    |-- source
    |-- summary
    |-- availability
    |-- profile_relevance
    |-- deduplication
    |-- parse_notes
    `-- metadata

## 4. identity

후보를 안정적으로 구분한다.

예시:

    identity:
      discovery_id: "incruit-0000000000000"
      provider: "incruit"
      external_id: "0000000000000"

필드:

- `discovery_id`: 내부 발견 항목 ID
- `provider`: 공고를 발견한 공급자
- `external_id`: 공급자가 부여한 공고 ID

`discovery_id`는 기본적으로 `{provider}-{external_id}` 형식을 사용한다.

## 5. source

어떤 경로에서 언제 발견했는지 기록한다.

예시:

    source:
      source_kind: "rss"
      feed_url: "https://www.incruit.com/rss/job.asp?occ1=150"
      source_url: "https://example.com/jobs/0000000000000"
      published_at: "2026-09-11T21:09:01+09:00"
      updated_at: null
      discovered_at: "2026-09-13T09:00:00+09:00"
      policy_checked_at: "2026-09-13"

권장 `source_kind` 값:

- rss
- official_api
- search_api
- ats_api
- sitemap
- json_ld
- permitted_html

`permitted_html`은 이용약관과 robots 정책을 모두 확인해 자동 접근이 허용된 경우에만 사용한다.

`updated_at`은 공급자가 명시적으로 제공할 때만 기록한다. Greenhouse Agent는 이 값이 없으면 공고가 그대로라고 추정하지 않고 기존 상세 분석을 재사용하지 않는다.

## 6. summary

발견 경로에서 직접 확인된 최소 메타데이터를 저장한다.

예시:

    summary:
      title: "비식별 예시 AI 자동화 엔지니어"
      company: "비식별 예시 기업"
      experience_text: "신입"
      education_text: "무관"
      location_text: "경기"
      deadline_text: "09/30"

확인되지 않은 값은 문자열 `unknown`으로 채우지 않고 `null`로 둔다.

## 7. availability

현재 후보가 어느 수준까지 처리 가능한지 기록한다.

예시:

    availability:
      content_scope: "metadata_only"
      detail_status: "unavailable"
      match_ready: false
      reason: "RSS에 주요 업무와 자격 요건 전문이 없음"

권장 `content_scope` 값:

- metadata_only
- summary
- full_posting

권장 `detail_status` 값:

- not_requested
- available
- unavailable
- policy_review_required
- fetch_failed

`match_ready`는 주요 업무, 필수 조건과 우대 조건을 근거와 함께 구조화할 수 있을 때만 `true`로 둔다.

## 8. profile_relevance

사용자가 별도 키워드를 입력하지 않아도 프로필에서 도출한 직무 축과 선호 조건으로 후보의 우선순위를 설명한다.

예시:

    profile_relevance:
      profile_id: "sample-user-001"
      related_target_role_ids:
        - "role-ai-automation"
      positive_signals:
        - "제목에 검색 확장어 'AI 자동화'가 포함됨"
      low_preference_signals: []
      location_assessment: "match"
      employment_assessment: "unknown"
      priority: "high"
      confidence: "medium"
      reason: "최우선 목표 직무 표현이 제목에 직접 나타나고 선호 지역과 일치함"

`related_target_role_ids`는 사용자 프로필의 `target_roles[].target_role_id`를 참조한다.

권장 판정 값:

- `location_assessment`: match, mismatch, unknown
- `employment_assessment`: match, mismatch, unknown
- `priority`: high, medium, low, review
- `confidence`: high, medium, low

`priority`는 최종 직무 적합도나 지원 추천이 아니다. 현재 발견 메타데이터만으로 상세 내용을 확인할 후보의 순서를 정한다.

낮은 선호 신호는 기본적으로 후보를 삭제하지 않고 우선순위의 근거로만 사용한다. 재택근무처럼 프로필에 확정되지 않은 조건은 묻거나 추정하지 않고 판정에서 제외한다.

## 9. deduplication

중복 판단에 사용한 키와 방식을 기록한다.

예시:

    deduplication:
      key: "incruit:0000000000000"
      strategy: "provider_external_id"

권장 `strategy` 값:

- provider_external_id
- provider_board_external_id
- canonical_url_hash

외부 ID가 있으면 URL 해시보다 우선한다.
기업 ATS처럼 같은 공급자 안에 여러 기업 보드가 있으면 `{provider}:{board_token}:{external_id}`를 중복 키로 사용한다.

## 10. parse_notes

파싱 과정에서 확인된 경고와 정보 부족을 저장한다.

예시:

    parse_notes:
      warnings: []
      unknowns:
        - "고용 형태"
        - "주요 업무"
        - "필수 조건"
        - "우대 조건"

파싱 실패를 임의 값으로 보완하지 않는다.

## 11. metadata

스키마와 예제 상태를 기록한다.

예시:

    metadata:
      schema_version: "1.0"
      is_example: true
      contains_real_posting_content: false

## 12. 필수 필드

첫 자동 발견 구현에서 반드시 필요한 필드는 다음과 같다.

- `identity.discovery_id`
- `identity.provider`
- `identity.external_id`
- `source.source_kind`
- `source.source_url`
- `source.discovered_at`
- `summary.title`
- `summary.company`
- `availability.content_scope`
- `availability.detail_status`
- `availability.match_ready`
- `profile_relevance.profile_id`
- `profile_relevance.related_target_role_ids`
- `profile_relevance.priority`
- `profile_relevance.reason`
- `deduplication.key`
- `deduplication.strategy`
- `metadata.schema_version`

## 13. 변환 규칙

인크루트 RSS 첫 변환은 다음 규칙을 사용한다.

- RSS `link`의 `job` 쿼리 값을 `external_id`로 사용한다.
- `author`를 회사명으로 우선 사용한다.
- `title`에서 회사명 접두사가 있으면 제거한 나머지를 공고 제목으로 사용한다.
- `description`에서는 회사명, 경력, 학력, 지역과 마감일만 읽는다.
- HTML 태그는 제거하고 표시용 텍스트만 저장한다.
- 상세 업무나 자격 요건을 `description`에 없는 정보로 추정하지 않는다.
- RSS에 상세 요건이 없으므로 기본 `match_ready`는 `false`다.
- 검색 확장어와 낮은 선호 신호는 사용자 프로필의 목표 직무 및 선호에서 생성한다.
- 수도권과 정규직처럼 프로필에 명시된 조건만 반영한다.
- 프로필에 없는 재택근무 선호는 생성하거나 사용자에게 필수 입력으로 요구하지 않는다.

## 14. 완료 기준

- 같은 공급자와 외부 ID가 같은 항목은 같은 중복 키를 가진다.
- 발견 시점과 원문 링크를 확인할 수 있다.
- 상세 분석 가능 여부가 명시되어 있다.
- 정보가 없는 필드가 추정값으로 채워지지 않는다.
- 공개 예제에 실제 공고 전문이나 개인정보가 포함되지 않는다.
- 후보 우선순위가 어떤 프로필 항목에서 도출됐는지 확인할 수 있다.
- 사용자가 검색 키워드와 제외 키워드를 별도로 작성하지 않아도 된다.
