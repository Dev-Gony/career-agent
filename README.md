# Career Agent

채용 매칭, 기술 격차 분석 및 포트폴리오 설계를 위한 개인용 AI 커리어 에이전트입니다.

Personal AI career agent for job matching, skill gap analysis, and portfolio planning.

## 프로젝트 목표

나의 실제 경력, 프로젝트, 기술 역량, 자기이해 자료를 하나의 프로파일로 구조화하고 실제 채용공고와 비교하여 다음 질문에 답하는 시스템을 만드는 것이 목표입니다.

- 이 직무가 나와 얼마나 맞는가?
- 어떤 경험과 역량이 강점으로 연결되는가?
- 현재 부족한 역량은 무엇인가?
- 무엇을 먼저 공부해야 하는가?
- 새로운 프로젝트가 필요한가, 기존 프로젝트를 확장하면 되는가?
- 지금 지원할 가치가 있는가?

초기 버전은 본인만 사용하는 개인용 Agent로 개발하고, 실제 사용을 통해 유용성을 확인한 뒤 채용공고 자동 수집과 정기 브리핑 기능까지 단계적으로 확장합니다.

## 핵심 원칙

- 실제 경력, 프로젝트, 행동 사례를 가장 중요한 판단 근거로 사용합니다.
- 성격검사와 적성검사는 직무를 단정하는 판정기가 아니라 보조 자료로 사용합니다.
- 적합도 숫자만 보여주지 않고 판단 근거를 함께 제공합니다.
- 부족한 기술이 발견됐다고 무조건 새 프로젝트를 만들지 않습니다.
- 기존 프로젝트를 확장하여 부족 역량을 증명할 수 있는지 먼저 검토합니다.
- 처음부터 모든 채용사이트를 자동화하지 않고 작은 MVP부터 검증합니다.

## 현재 개발 단계

현재는 실제 ATS 공고 자동 입력 검증 단계입니다.

완료:

- 프로젝트 저장소 생성
- 저장소 공통 작업 규칙 작성
- MVP 요구사항 정의
- 사용자 프로파일 데이터 구조 설계
- 비식별 사용자 프로파일 예제 작성
- 채용공고 데이터 구조 및 예제 작성
- 근거 기반 매칭 규칙 정의
- 매칭 결과 구조 및 기대 결과 예제 작성
- 개인정보 및 비밀정보 제외 규칙 추가
- 입력과 결과 사이의 안정적인 ID 참조 검증
- 프로필 기반 자동 검색 계획과 후보 우선순위 기대 사례 작성
- 합성 인크루트 RSS와 발견 레코드의 변환 계약 작성
- 합성 RSS 항목 1개를 프로필 기반 발견 레코드로 변환하는 기능 구현
- 정상 변환, 필수 필드 누락과 위험한 XML 구조에 대한 단위 테스트 작성
- RSS 여러 항목을 독립적으로 변환하고 항목별 오류를 분리하는 기능 구현
- 로컬 JSON 저장소를 이용한 실행 간 중복 제거 구현
- 허용된 인크루트 RSS만 읽는 네트워크 함수 구현
- 실제 RSS 20개를 로컬 저장하고 다음 실행에서 중복 20개로 판정하는 실행 명령 구현
- 저장된 후보를 우선순위, 회사, 제목, 지역과 원문 링크로 확인하는 로컬 목록 구현
- 구조화된 공고의 기술 요구사항을 사용자 프로필 증거와 비교하는 최소 매처 구현
- REST API 연동과 자동화 프로젝트 요구사항을 프로젝트·행동 증거와 비교하는 경험 매처 구현
- 기술·경험 판정을 공고 원래 순서로 합치는 통합 요구사항 매처 구현
- 경력·학력·지역·고용 형태를 역량과 분리해 판정하는 지원 가능 조건 매처 구현
- 필수·우대·지원 가능 조건을 조합하는 근거 기반 지원 추천 구현
- 공고 주요 업무를 사용자 기술·프로젝트·행동 증거에 연결하는 업무 매처 구현
- 판정 근거에서 지원 강점, 확인된 부족과 미확인 항목을 생성하는 인사이트 기능 구현
- Greenhouse 공개 Job Board API의 상세 공고 1건을 내부 스키마로 변환하는 조회 전용 연동 구현
- 실제 Sendbird 서울 AI 공고를 로컬 파일로 구조화하고 기존 매칭기에 연결해 전체 흐름 확인
- Greenhouse 공고 조회부터 매칭과 결과 JSON 저장까지 한 명령으로 실행하는 워크플로 구현

다음 단계:

1. 실제 상세 공고 결과에서 중요한 복합 조건의 추출·판정 범위를 보강
2. ATS 공고 발견과 상세 구조화를 한 실행 흐름으로 연결
3. 저장된 실제 분석 결과의 사용자 검토와 판정 교정 반영
4. 문서 입력과 대화가 가능한 첫 Slack 인터페이스 설계 및 구현
5. 하루 1회 실행과 성공·실패 상태 기록

## 저장소 구조

    career-agent/
    |-- AGENTS.md
    |-- README.md
    |-- docs/
    |   |-- PRD.md
    |   |-- USER_PROFILE_SCHEMA.md
    |   |-- JOB_POSTING_SCHEMA.md
    |   |-- JOB_DISCOVERY_PLAN.md
    |   |-- JOB_DISCOVERY_SCHEMA.md
    |   |-- JOB_SEARCH_PLAN_SCHEMA.md
    |   |-- INCRUIT_RSS_MAPPING.md
    |   |-- GREENHOUSE_API_MAPPING.md
    |   |-- MATCHING_RULES.md
    |   `-- MATCH_RESULT_SCHEMA.md
    |-- data/
    |   |-- user_profile.example.json
    |   |-- job_posting.example.json
    |   |-- job_discovery.example.json
    |   |-- job_search_plan.example.json
    |   |-- job_discovery_ranking_cases.example.json
    |   |-- incruit_rss_item.example.xml
    |   `-- match_result.example.json
    |-- src/
    |   `-- career_agent/
    |       |-- discovery/
    |       |   |-- incruit_feed.py
    |       |   |-- incruit_rss.py
    |       |   |-- report.py
    |       |   |-- service.py
    |       |   `-- store.py
    |       |-- ingestion/
    |       |   `-- greenhouse.py
    |       |-- matching/
    |       |   |-- eligibility.py
    |       |   |-- experience.py
    |       |   |-- insights.py
    |       |   |-- recommendation.py
    |       |   |-- responsibility.py
    |       |   |-- service.py
    |       |   `-- technology.py
    |       `-- workflows/
    |           `-- greenhouse_analysis.py
    |-- scripts/
    |   |-- analyze_greenhouse_job.py
    |   |-- discover_incruit.py
    |   |-- list_discoveries.py
    |   |-- import_greenhouse_job.py
    |   |-- match_job.py
    |   |-- match_job_experiences.py
    |   `-- match_job_technologies.py
    |-- tests/
    |   |-- test_application_recommendation.py
    |   |-- test_greenhouse_analysis_workflow.py
    |   |-- test_discovery_report.py
    |   |-- test_discovery_service.py
    |   |-- test_incruit_rss.py
    |   |-- test_incruit_feed.py
    |   |-- test_greenhouse_ingestion.py
    |   |-- test_match_insights.py
    |   |-- test_discovery_store.py
    |   |-- test_eligibility_matching.py
    |   |-- test_experience_matching.py
    |   |-- test_requirement_matching_service.py
    |   |-- test_responsibility_matching.py
    |   `-- test_technology_matching.py
    `-- 작업일지.md

## 문서

### docs/PRD.md

프로젝트의 문제 정의, MVP 범위, 핵심 기능, 성공 기준과 향후 확장 계획을 정리합니다.

### docs/USER_PROFILE_SCHEMA.md

경력, 프로젝트, 기술 역량, 행동 사례, 자기이해 검사, 업무 및 학습 성향을 Career Agent가 읽을 수 있는 표준 구조로 정의합니다.

### docs/JOB_POSTING_SCHEMA.md

채용공고의 주요 업무, 필수 조건, 우대 조건과 출처 정보를 비교 가능한 구조로 정의합니다.

### docs/JOB_DISCOVERY_PLAN.md

공식 API, RSS, 검색엔진, 기업 ATS와 제한적인 직접 수집을 비교하고 개인용 MVP의 자동 공고 발견 경계를 정의합니다.

### docs/JOB_DISCOVERY_SCHEMA.md

RSS나 공식 API에서 발견한 후보를 상세 분석 전 단계에서 저장하기 위한 최소 구조를 정의합니다.

### docs/JOB_SEARCH_PLAN_SCHEMA.md

사용자가 검색 조건을 다시 입력하지 않아도 프로필에서 직무 축, 역량 신호와 후보 정렬 기준을 생성하는 구조를 정의합니다.

### docs/INCRUIT_RSS_MAPPING.md

비식별 합성 인크루트 RSS 항목을 발견 레코드로 변환하는 필드별 계약과 실패 처리 범위를 정의합니다.

### docs/GREENHOUSE_API_MAPPING.md

Greenhouse 공개 Job Board API 공고를 내부 채용공고 스키마로 변환하는 기준과 조회 전용 접근 경계를 정의합니다.

### docs/MATCHING_RULES.md

실제 증거의 우선순위, 일치 수준, 부족과 정보 부족의 구분 및 지원 판단 원칙을 정의합니다.

### docs/MATCH_RESULT_SCHEMA.md

공고 요구사항과 사용자 근거를 연결한 판정, 부족 역량, 추천과 지원 판단의 결과 구조를 정의합니다.

## 현재 구현 실행

현재 구현은 Python 표준 라이브러리만 사용하며 별도 패키지 설치가 필요하지 않습니다.

저장소 루트에서 다음 명령으로 테스트합니다.

    python -m unittest discover -s tests -v

실제 인크루트 RSS에서 신규 후보를 발견하고 로컬에 저장합니다.

    python scripts/discover_incruit.py

실제 발견 결과는 Git에서 제외된 `private-data/discoveries.json`에 저장됩니다. 명령 출력에는 처리 건수, 오류 건수, 신규 및 중복 건수와 우선순위 집계만 표시됩니다.

저장된 후보를 로컬 목록으로 확인합니다.

    python scripts/list_discoveries.py --limit 10

특정 발견 우선순위만 확인할 수도 있습니다.

    python scripts/list_discoveries.py --priority high --limit 10

예제 사용자 프로필과 예제 공고의 기술 요구사항만 비교합니다.

    python scripts/match_job_technologies.py

다른 구조화된 입력 파일은 `--profile`과 `--posting`으로 지정할 수 있습니다. 현재 이 명령은 `skill`과 `cloud` 유형만 평가하며 업무 경험, 지원 조건과 최종 지원 추천은 아직 만들지 않습니다.

예제 공고의 경험 요구사항을 프로젝트와 행동 증거에 연결합니다.

    python scripts/match_job_experiences.py

이 명령은 현재 REST API 연동과 자동화 프로젝트 경험을 판정합니다. 해석 규칙이 없는 경험은 부족으로 단정하지 않고 `unknown`으로 남깁니다.

기술과 경험 판정을 공고의 원래 순서로 합쳐 확인합니다.

    python scripts/match_job.py

통합 명령은 아직 평가하지 못하는 조건도 결과에서 누락하지 않고 `unknown`으로 표시합니다. 필수·우대 조건, 주요 업무, 경력·학력·지역·고용 형태, 지원 강점·부족·미확인 항목과 근거 기반 지원 추천을 출력합니다. 추천은 합격 확률이 아니라 현재 프로필과 공고의 비교 결과입니다.

Greenhouse를 사용하는 기업의 공개 상세공고 1건을 자동으로 구조화합니다. board token과 job ID는 해당 기업의 공개 채용 URL 또는 API에서 확인한 값을 사용합니다.

공고 조회, 구조화, 프로필 비교와 분석 JSON 저장을 한 번에 실행합니다.

    python scripts/analyze_greenhouse_job.py --board sendbird --job-id 8395379002

결과는 기본적으로 `private-data/analysis-greenhouse-<board>-<job-id>.json`에 저장됩니다. 분석 ID, 생성 시각, 입력 공고 URL, 요구사항별 판정, 강점·부족·미확인 항목과 지원 판단이 포함됩니다. 사용자 프로필 원문은 결과에 복제하지 않으며 사용자 검토 전 상태는 `not_reviewed`입니다.

공고 구조화 결과만 따로 확인하려면 다음 하위 단계 명령을 사용합니다.

    python scripts/import_greenhouse_job.py --board sendbird --job-id 8395379002

기본 출력은 Git에서 제외된 `private-data/greenhouse-<board>-<job-id>.json`입니다. 공고 전문은 저장하지 않으며, 인식된 주요 업무·필수 조건·우대 조건과 원문 URL을 저장합니다.

구조화된 실공고를 기존 매칭기에 넣습니다.

    python scripts/match_job.py --posting private-data/greenhouse-sendbird-8395379002.json

현재 예시 ID는 2026-09-13 실제 공개 상태를 확인한 값이므로 이후 공고가 마감되면 API 조회가 실패할 수 있습니다.

현재 테스트 범위:

- 합성 RSS 항목을 기대 발견 레코드로 변환
- RSS 여러 항목 중 정상 항목 보존과 항목별 오류 분리
- 제목이 없는 RSS 항목 거부
- `DOCTYPE` 또는 `ENTITY`가 포함된 XML 거부
- 같은 공고의 실행 간 중복 제거
- 손상된 로컬 저장 파일 보호
- 허용되지 않은 RSS 호스트와 과도한 응답 크기 거부
- RSS 읽기, 변환, 프로필 기반 정렬과 중복 저장의 전체 실행 조합
- 한글과 지역 구분자를 정리한 로컬 후보 목록 출력
- 프로젝트 수준 기술의 강한 일치와 학습 수준 기술의 부분 일치 판정
- 실제 사용이 없다고 확인된 노출 경험과 프로필 정보 부재의 `gap`/`unknown` 구분
- REST API 연동 요구와 기술·완료 프로젝트 증거 연결
- 자동화 프로젝트 요구와 완료 프로젝트·행동 증거 연결
- 계획 중 프로젝트와 근거가 없는 경험의 `partial`/`unknown` 구분
- 기술·경험 판정을 안정적인 항목 ID로 조합하고 공고 원래 순서 유지
- 지원하지 않는 조건 유형의 누락 방지와 `unknown` 처리
- 필수와 우대 조건의 분리 집계
- 최소·최대 경력 연수와 비공개 경력 정보의 `met`·`not_met`·`needs_confirmation` 구분
- 필수 학력 정보 부재와 학력 조건 없음의 `needs_confirmation`·`not_applicable` 구분
- 수도권 지역 포함 관계와 정규직·계약직 등 고용 형태 정규화
- 단순 선호 불일치를 자동 지원 불가로 처리하지 않는 조건 판정
- 필수 역량 부족, 필수 조건 미확인과 지원 불가 조건을 구분한 지원 판단
- 우대 조건 부족을 지원 보류 사유가 아닌 주의사항으로 처리
- 추천 신뢰도와 합격 가능성 예측의 명시적 분리
- 반복 업무 자동화, API 연동과 LLM 도구 개발 업무의 프로젝트 증거 연결
- 기본 로그 확인·재시도와 능동 실패 알림을 구분한 모니터링 업무 판정
- 근거 없는 주요 업무의 `unknown` 유지와 지원 추천 재조정
- 여러 판정에 반복 연결된 프로젝트와 기술 증거의 강점 우선순위 정렬
- 필수·우대·지원 불가 조건의 `immediate`·`preferred_only`·`blocking` 부족 구분
- 정보 부재를 부족으로 바꾸지 않는 미확인 항목 생성
- 허용된 Greenhouse 공개 API의 GET 요청과 외부 리디렉션 거부
- Greenhouse 본문의 필수·우대·주요 업무 섹션 분리
- 명시된 경력 연수·서울 지역·하이브리드 근무 추출과 고용 형태 미추정
- Greenhouse 조회·구조화·매칭 결과의 단일 실행과 저장 가능한 분석 메타데이터 생성
- 저장 결과에 사용자 프로필 원문을 복제하지 않고 검토 전 상태 유지

현재 구현은 공식 인크루트 RSS를 읽고 로컬 JSON에 신규 후보를 저장하며, 구조화된 공고의 기술·경험 요구사항, 주요 업무와 지원 가능 조건을 비교해 강점·부족·미확인 항목과 지원 판단을 생성합니다. Greenhouse 공개 API의 상세 공고 1건은 사용자의 복사·붙여넣기 없이 한 명령으로 조회·분석·저장할 수 있습니다. 아직 LLM 호출, 발견 후보와 상세 입력의 자동 연결 또는 Slack 연동은 하지 않습니다.

## 예상 MVP 흐름

    사용자 프로파일
            |
            v
    채용공고 입력
            |
            v
    요구사항 추출
            |
            v
    사용자와 비교
            |
            v
    적합도 및 근거 분석
            |
            v
    부족 역량 분석
            |
            v
    학습 및 포트폴리오 추천
            |
            v
    지원 판단

구현 전 검증에는 고정된 예제 공고를 사용합니다. 이는 매칭 규칙을 재현하기 위한 테스트 입력이며, 사용자가 공고를 계속 복사해 붙여넣는 방식을 최종 제품 흐름으로 삼지 않습니다. 개인용 MVP의 실제 입력은 이용 조건을 지키는 자동 발견 경로부터 작은 범위로 연결합니다.

## 향후 확장 방향

MVP가 실제로 유용하다고 판단되면 다음 기능을 검토합니다.

- 사람인, 잡코리아, 인크루트, 원티드 등 채용공고 수집
- 신규 공고 중복 제거
- 공고별 개인 적합도 분석
- 지원 우선순위 추천
- 부족 역량 및 학습 로드맵 추천
- 기존 포트폴리오 개선안 추천
- 채용시장에서 자주 요구되는 기술 통계
- Slack 또는 이메일 정기 취업 브리핑
- 지원 일정 및 면접 준비 관리

외부 채용사이트 데이터 수집은 각 사이트의 이용약관, robots 정책, 공개 API 제공 여부를 확인한 뒤 적절한 방식으로 구현합니다.

## 개인정보와 보안

이 저장소는 Public입니다.

따라서 다음 정보는 저장소에 올리지 않습니다.

- 자기이해 검사 원본 PDF
- 개인 연락처
- 상세 주소
- 개인 이메일
- 인증정보
- API Key
- Access Token
- Webhook URL
- 기타 공개할 필요가 없는 개인정보

실제 개인 프로파일은 향후 `private-data/` 같은 Git 제외 영역에 저장하고, 공개 저장소에는 비식별 예제 데이터만 포함합니다.

## 프로젝트 상태

현재 상태: 자동 공고 발견, 공식 ATS 상세 입력 및 핵심 근거 기반 매칭 구현

공식 인크루트 RSS를 읽어 프로필 기반 발견 레코드로 변환하고 실행 간 중복을 제거해 로컬에 저장하는 첫 동작 가능한 기능을 구현했습니다. 실제 첫 실행은 신규 20건, 두 번째 실행은 신규 0건과 중복 20건으로 확인했습니다. Greenhouse 공개 Job Board API에서는 실제 Sendbird 서울 AI 공고 1건을 한 명령으로 조회·구조화·매칭하고 분석 ID가 있는 로컬 JSON으로 저장했습니다. 실공고 결과는 Python과 LLM API 증거를 연결했고, 사용자 경력 연수·고용 형태·하이브리드 근무 선호가 확인되지 않은 점은 조건부로 남겼습니다. 다음에는 실제 결과에서 중요한 복합 조건을 보강하고 발견 후보에서 상세 분석으로 이어지는 한 흐름을 연결합니다.
