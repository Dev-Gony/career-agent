# Greenhouse Job Board API Mapping

## 1. 목적

기업이 Greenhouse에 공개한 상세 채용공고 1건을 사용자의 복사·붙여넣기 없이 `JOB_POSTING_SCHEMA`로 변환하는 첫 ATS 연동 계약을 정의한다.

ATS는 Applicant Tracking System의 약자로 기업이 채용공고와 지원 절차를 관리하는 시스템이다.

## 2. 확인한 공식 제공 범위

- Greenhouse Job Board API의 GET 공고 데이터는 공개 조회용이며 인증이 필요하지 않다.
- 현재 게시 공고 목록 조회 엔드포인트는 `GET /v1/boards/{board_token}/jobs`다.
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

목록 조회에서는 `content=true`를 사용하지 않는다. 제목, 회사, 근무지, 공고 ID와 원문 URL만 후보 선별에 사용하고 상세 본문은 선별된 공고를 실제 분석할 때 별도 1건 조회로 가져온다.

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

## 8. 자동 발견에서 상세 분석으로 넘기는 경계

현재 Agent 실행은 외부 조회량과 잘못된 자동 확장을 줄이기 위해 다음 순서를 지킨다.

1. 설정에 활성화된 모든 기업 보드의 현재 공고 목록만 먼저 조회한다.
2. 프로필 기반 우선순위가 `high`인 공고만 상세 분석 후보로 삼는다.
3. 모든 성공 보드의 현재 `high` 후보를 합치고 게시 시점이 가장 최근인 1건만 상세 조회한다.
4. 현재 목록에 `high` 후보가 없으면 상세 조회 없이 정상 종료한다.
5. 로컬 저장소에 남아 있지만 현재 기업 보드 목록에는 없는 과거 공고는 선택하지 않는다.
6. 선택한 공고의 상세 조회나 분석이 실패해도 다른 후보를 연쇄적으로 조회하지 않는다.
7. 일부 보드의 목록 조회 실패는 기록하고 나머지 보드를 계속 처리하지만 모든 보드가 실패하면 종료한다.

이 제한은 합격 가능성을 자동 예측하기 위한 것이 아니라 사용자가 검토할 가치가 높은 현재 공고 1건을 근거 기반 비교 단계로 안전하게 전달하기 위한 것이다.

## 9. 기존 분석 재사용 기준

현재 목록에서 선택된 공고가 이전에 분석됐더라도 다음 값이 모두 같을 때만 상세 조회와 매칭을 반복하지 않는다.

- Greenhouse board token과 공고 ID
- 목록 API가 제공한 공고 `updated_at`
- 사용자 프로필 전체 내용의 SHA-256 지문
- 매칭 규칙 버전
- 공고 구조화와 분석 파이프라인 버전

이전 결과에 비교 값이 없거나 값 하나라도 다르면 새 분석을 실행한다. 재사용할 때는 기존 분석 파일을 덮어쓰거나 같은 내용의 새 파일을 만들지 않는다.
