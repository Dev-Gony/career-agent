# Incruit RSS Mapping

## 1. 목적

인크루트 RSS 항목 1개를 `JOB_DISCOVERY_SCHEMA`의 발견 레코드 1개로 변환하는 계약을 정의한다.

이 문서는 네트워크 호출이나 파서 구현 방법을 정의하지 않는다. 합성 입력과 기대 출력 사이에서 어떤 값이 어떻게 이동해야 하는지만 고정한다.

## 2. 검증 파일

- 합성 입력: `data/incruit_rss_item.example.xml`
- 기대 출력: `data/job_discovery.example.json`
- 검색 계획: `data/job_search_plan.example.json`

합성 입력에는 실제 회사명, 실제 공고 제목이나 실제 인크루트 공고 URL을 넣지 않는다.

## 3. 처리 단계

변환은 두 단계로 나눈다.

1. RSS 정규화: RSS 필드를 발견 레코드의 식별자, 출처와 요약으로 변환한다.
2. 프로필 기반 정렬: 검색 계획을 적용해 `profile_relevance`를 만든다.

RSS 정규화만 성공해도 후보는 저장할 수 있다. 프로필 기반 정렬에 실패하면 후보를 삭제하지 않고 `priority: review`와 경고를 남긴다.

## 4. 입력 형식 확인

첫 파서는 다음 구조만 처리한다.

    rss
    `-- channel
        `-- item
            |-- title
            |-- link
            |-- description
            |-- author
            `-- pubDate

`rss/channel/item`이 없으면 정상 RSS 항목으로 처리하지 않는다. 예상하지 못한 HTML, 인증 화면 또는 CAPTCHA 응답은 파싱하지 않고 수집을 중단한다.

## 5. 필드 변환 계약

| 입력 | 출력 | 변환 규칙 |
| --- | --- | --- |
| `item/link`의 `job` 쿼리 값 | `identity.external_id` | 문자열 그대로 사용 |
| 공급자 이름 | `identity.provider` | `incruit` 고정 |
| 공급자와 외부 ID | `identity.discovery_id` | `{provider}-{external_id}` |
| 실행 설정 | `source.source_kind` | `rss` 고정 |
| RSS 주소 | `source.feed_url` | 설정에 사용한 공식 RSS URL |
| `item/link` | `source.source_url` | 원문 링크 그대로 저장 |
| `item/pubDate` | `source.published_at` | RFC 822 시간을 ISO 8601로 변환하고 시간대 유지 |
| 실제 발견 시각 | `source.discovered_at` | 실행 시점의 Asia/Seoul 시각 |
| 정책 확인일 | `source.policy_checked_at` | 마지막 정책 검토일 |
| `item/title` | `summary.title` | 정확히 일치하는 `[회사명]` 접두사만 제거 |
| `item/author` | `summary.company` | 비어 있지 않으면 우선 사용 |
| `description`의 경력 | `summary.experience_text` | HTML 태그 제거 후 표시 문자열 유지 |
| `description`의 학력 | `summary.education_text` | HTML 태그 제거 후 표시 문자열 유지 |
| `description`의 지역 | `summary.location_text` | 구분 기호를 정리하되 원문 의미 유지 |
| `description`의 마감일 | `summary.deadline_text` | 연도를 추정하지 않고 표시 문자열 유지 |
| 공급자와 외부 ID | `deduplication.key` | `{provider}:{external_id}` |

## 6. 회사명과 제목 규칙

회사명 우선순위:

1. `author`
2. `description`의 `회사명`
3. 둘 다 없으면 `null`과 경고

제목에서 회사명 접두사를 제거하는 예:

    입력: [비식별 예시 기업] 비식별 예시 AI 자동화 엔지니어
    회사: 비식별 예시 기업
    출력: 비식별 예시 AI 자동화 엔지니어

대괄호 안의 문자열이 확인된 회사명과 다르면 임의로 제거하지 않는다.

## 7. description 규칙

첫 파서는 다음 라벨만 읽는다.

- 회사명
- 경력
- 학력
- 지역
- 마감일

`<br>` 태그는 항목 구분자로만 사용한다. 지원 현황 링크나 다른 HTML이 포함되어도 링크 텍스트를 자격 요건으로 해석하지 않는다.

라벨이 없거나 값이 비어 있으면 해당 출력 필드를 `null`로 두고 `parse_notes.unknowns`에 추가한다.

## 8. 상세 분석 준비 상태

인크루트 RSS에는 주요 업무와 필수 및 우대 조건 전문이 없으므로 다음 값으로 시작한다.

    availability:
      content_scope: "metadata_only"
      detail_status: "unavailable"
      match_ready: false
      reason: "RSS에 주요 업무와 자격 요건 전문이 없음"

이 단계에서 `MATCH_RESULT_SCHEMA`의 결과를 생성하지 않는다.

## 9. 프로필 기반 정렬 계약

정규화된 제목, 지역과 고용형태에 `job_search_plan`을 적용한다.

합성 예제의 기대 판단:

- 제목의 `AI 자동화`가 `role-ai-automation`과 직접 관련된다.
- `경기`는 프로필의 `수도권` 정규화 값에 포함된다.
- RSS에는 고용형태가 없으므로 `employment_assessment`는 `unknown`이다.
- 직접 관련성과 지역 일치를 근거로 발견 우선순위는 `high`다.
- 상세 내용이 없으므로 신뢰도는 `medium`, `match_ready`는 `false`다.

이 판단에는 사용자가 별도로 입력한 포함 키워드, 제외 키워드나 재택 선호를 사용하지 않는다.

## 10. 실패와 대체 규칙

- `title`이 없으면 후보를 만들지 않고 항목 오류를 기록한다.
- `link`가 없으면 원문 확인이 불가능하므로 후보를 만들지 않고 항목 오류를 기록한다.
- `job` 외부 ID가 없으면 canonical URL 해시를 대체 중복 키로 사용할 수 있다.
- `author`가 없으면 description의 회사명을 사용한다.
- `pubDate`가 없거나 해석되지 않으면 `published_at`을 `null`로 두되 발견 자체는 유지한다.
- description 일부가 누락되어도 확인된 필드만 저장하고 후보는 유지한다.
- 오류가 발생해도 존재하지 않는 값이나 자격 요건을 추정하지 않는다.

## 11. 첫 구현 범위

이 계약이 승인된 뒤 첫 실행 코드는 다음 한 가지 책임만 가진다.

    합성 RSS item 1개
        -> 정규화된 발견 레코드 1개

첫 구현에 포함하지 않는 것:

- 실제 인크루트 네트워크 호출
- 예약 실행
- 여러 항목 반복 처리
- 데이터베이스 저장
- LLM 호출
- 상세 페이지 접근
- 최종 적합도 분석
- 알림 전송

## 12. 완료 기준

- 합성 XML이 정상적인 XML로 파싱된다.
- 외부 ID, 제목, 회사, 게시 시점, 경력, 학력, 지역과 마감일이 기대 출력과 일치한다.
- 발견 ID와 중복 키가 규칙대로 생성된다.
- 고용형태가 없다는 사실이 `unknown`으로 유지된다.
- `match_ready`가 `false`로 유지된다.
- 실제 공고 내용이 공개 예제에 포함되지 않는다.
