# Greenhouse Board Configuration Schema

## 1. 목적

Agent가 접근할 공식 Greenhouse 기업 보드를 코드에 직접 고정하지 않고 검증 가능한 로컬 소스 등록부로 관리한다.

이 설정은 사용자가 직무 검색 키워드를 다시 입력하는 문서가 아니다. Agent가 공식 채용 URL과 접근 정책을 확인한 소스를 기록하는 문서다.

## 2. 현재 MVP 경계

- `enabled: true`인 보드가 1개 이상 있어야 한다.
- 개인용 MVP의 목록 요청량을 제한하기 위해 활성 보드는 최대 10개까지 허용한다.
- 활성 보드의 현재 목록을 먼저 모두 조회한 뒤 `high` 후보를 합산한다.
- 활성 보드 수와 관계없이 상세 분석은 전체에서 최대 1건만 실행한다.
- 한 보드의 목록 조회가 실패하면 오류를 기록하고 다른 보드 조회는 계속한다.
- 모든 보드의 목록 조회가 실패하면 상세 분석 없이 오류로 종료한다.
- 등록된 `careers_url`은 인증정보가 없는 HTTPS URL이어야 한다.
- `board_token`은 영문자, 숫자, 밑줄과 하이픈만 허용한다.
- 같은 `board_token`은 대소문자와 관계없이 중복 등록할 수 없다.
- `policy_checked_at`은 해당 소스의 접근 방법을 마지막으로 확인한 날짜다.

후보의 게시 시각은 표기 문자열이 아니라 시간대가 반영된 실제 시각으로 비교한다. 가장 최근의 현재 `high` 후보 1건을 선택한 뒤에는 상세 분석 실패 시 다른 후보로 자동 확장하지 않는다.

## 3. 구조

    {
      "greenhouse_boards": {
        "boards": [
          {
            "board_token": "sendbird",
            "company": "Sendbird",
            "careers_url": "https://sendbird.com/careers",
            "access_method": "greenhouse_job_board_api",
            "policy_checked_at": "2026-09-14",
            "enabled": true
          }
        ],
        "metadata": {
          "schema_version": "1.0"
        }
      }
    }

## 4. 필드

| 필드 | 의미 |
| --- | --- |
| `board_token` | Greenhouse 공개 Job Board API 경로에 사용하는 기업 보드 식별자 |
| `company` | 사람이 확인할 기업명 |
| `careers_url` | board token을 확인한 공식 기업 채용페이지 |
| `access_method` | 허용된 조회 방식이며 현재는 `greenhouse_job_board_api`만 가능 |
| `policy_checked_at` | 공개 조회 범위와 접근 정책을 확인한 날짜 |
| `enabled` | 현재 실행 대상으로 사용할지 여부 |

## 5. 공개 예제와 개인 설정

- 공개 예제: `data/greenhouse_boards.example.json`
- 개인 설정 권장 경로: `private-data/greenhouse_boards.json`

`private-data/`는 Git에서 제외된다. 기업 목록 자체는 보통 공개 정보지만 사용자의 관심 기업 조합은 개인 구직 의도를 드러낼 수 있으므로 개인 설정은 공개 저장소에 올리지 않는다.
