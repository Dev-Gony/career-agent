# Greenhouse Job Board API Mapping

## 1. 목적

기업이 Greenhouse에 공개한 상세 채용공고 1건을 사용자의 복사·붙여넣기 없이 `JOB_POSTING_SCHEMA`로 변환하는 첫 ATS 연동 계약을 정의한다.

ATS는 Applicant Tracking System의 약자로 기업이 채용공고와 지원 절차를 관리하는 시스템이다.

## 2. 확인한 공식 제공 범위

- Greenhouse Job Board API의 GET 공고 데이터는 공개 조회용이며 인증이 필요하지 않다.
- 공고 1건 조회 엔드포인트는 `GET /v1/boards/{board_token}/jobs/{job_id}`다.
- 지원서 제출은 별도 인증이 필요한 POST 영역이며 현재 MVP에서 사용하지 않는다.

공식 문서:

- <https://docs.greenhouse.io/job-board.html>
- <https://support.greenhouse.io/hc/en-us/articles/10568627186203-Greenhouse-API-overview>

## 3. 접근 경계

현재 구현은 다음 조건만 허용한다.

- HTTPS
- 호스트 `boards-api.greenhouse.io`
- 검증된 board token과 숫자 job ID
- GET 요청
- JSON 응답
- 최대 2 MB 응답
- 요청 주소와 같은 공식 API 경로로 끝나는 응답

HTML 채용페이지 직접 크롤링, 지원서 제출, 인증 우회와 비공식 내부 API 사용은 하지 않는다.

## 4. 변환 기준

API 응답의 직접 필드:

| API 필드 | 내부 필드 |
| --- | --- |
| `id` | `identity.posting_id`, `source.external_job_id` |
| `title` | `identity.title`, `role.normalized_title` |
| `company_name` | `company.name` |
| `location.name` | `location.region` |
| `absolute_url` | `source.url` |
| `updated_at` | `source.updated_at` |
| `content` | 구조화할 섹션 입력 |

본문은 명시적인 섹션 제목이 인식될 때만 다음처럼 분류한다.

- `What you'll actually do`, `Responsibilities`, `주요 업무`: `responsibilities`
- `You need to have`, `Requirements`, `자격 요건`: `requirements`
- `Added Value`, `Preferred Qualifications`, `우대 사항`: `preferred_qualifications`
- `The Role`, `About the Role`, `직무 소개`: `role.summary`

기술명은 Python, LLM API, REST API, LangChain/LangGraph, AWS, GCP처럼 명시된 경우만 표준 이름으로 바꾼다. 하나의 문장에 복합 조건이 있으면 임의로 쪼개지 않고 원문 조건을 유지한다.

## 5. 추정하지 않는 값

- 제목 또는 본문에 명시되지 않은 고용 형태
- 숫자로 명시되지 않은 경력 연수
- 공고에 없는 학력, 연봉, 기업 규모와 산업
- 자유 서술형 조건의 사용자 충족 여부
- 합격 가능성

확인할 수 없는 항목은 `unknown` 또는 매칭 결과의 `needs_confirmation`으로 남긴다.

## 6. 저장 경계

- 실제 API 결과는 기본적으로 Git 제외 경로인 `private-data/`에 저장한다.
- 공고 전문은 결과 JSON에 저장하지 않는다.
- 필수 조건, 우대 조건과 주요 업무로 구조화된 문장과 원문 URL만 남긴다.
- 공개 테스트에는 실제 기업 공고 대신 비식별 합성 응답을 사용한다.

## 7. 현재 한계

- 회사마다 다른 자유 형식 섹션 제목을 모두 인식하지 못한다.
- 한 문장에 여러 조건이 결합된 경우 세부 조건별 판정이 제한된다.
- 영어, 시스템 설계, 멘토링 같은 조건은 현재 매처에서 `unknown`이 될 수 있다.
- Greenhouse를 사용하지 않는 기업에는 이 연동을 적용할 수 없다.

이 한계를 숨기지 않고 실제 공고 1건의 결과를 먼저 검토한 뒤 추출 규칙 또는 LLM 보조 추출의 필요성을 판단한다.
