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

현재는 실제 Slack 명령으로 다음 공고 1건 분석과 스레드 요약 응답을 검증했고, 실제 첨부 문서의 승인된 Gemini 분석 초안을 영구 프로필과 분리된 임시 검색 프로필로 사용해 공식 공고를 찾는 단계까지 연결했습니다.

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
- Greenhouse 기업 보드의 현재 공고 목록을 조회하고 프로필 목표 직무와 선호 조건으로 후보를 정렬하는 기능 구현
- Greenhouse 현재 목록의 `high` 후보 1건을 공고 ID 입력 없이 상세 분석하고 실행별 결과로 저장하는 제한된 Agent 워크플로 구현
- 공고 갱신 시각, 프로필 내용과 분석 규칙이 같으면 기존 상세 분석을 재사용하는 반복 실행 제한 구현
- 검증된 Greenhouse 기업 보드를 코드 밖의 소스 등록부에서 읽는 설정 구현
- 여러 보드의 현재 목록을 합산하되 전체에서 가장 최근 `high` 후보 1건만 상세 분석하는 전역 실행 제한 구현
- 새 분석, 기존 분석 재사용, 무후보와 실패 실행을 프로필·공고 본문 없이 별도 로컬 이력으로 저장하는 기능 구현
- 사용자 문서 원본의 비공개 저장, Slack 저장 직후 후보 추출과 비확정 근거 신호 요약 구현
- 프로필 후보별 승인·거부 불변 기록 구현
- 프로필 분석 초안 항목별 승인·거부 불변 기록 구현
- 후보별 최신 판단 중 승인된 항목만 기존 프로필과 분리된 갱신안으로 만드는 기능 구현
- 승인된 기술 후보를 기존 기술 중복, 세부정보 필요와 기술명 분리 필요로 구분하는 비파괴 매핑 구현
- 새 기술 후보의 숙련도와 사용 증거를 명시적 사용자 확인 기록으로 저장하는 기능 구현
- 최신 사용자 확인이 있는 새 기술 후보만 완성된 기술 추가안으로 만드는 기능 구현
- 완성된 기술 추가안 한 건의 최종 승인·거부를 기술 내용과 분리해 기록하는 기능 구현
- 최신 최종 승인이 있는 기술만 원본을 보존한 새 프로필 버전에 적용하는 기능 구현
- Slack `app_mention` 합성 이벤트의 허용 사용자·채널 검증과 첫 명령 라우팅 구현
- 최소 권한 Slack App manifest와 Token 비노출 로컬 준비 검사 구현
- Slack Bot Token 인증, Socket Mode App Token 사용 가능 여부와 개인 허용 목록 설정 검증 구현
- 공식 Slack Bolt SDK 기반 Socket Mode 수신기와 비실행 확인 응답 구현
- 실제 Slack 채널의 봇 호출 수신과 스레드 확인 응답 검증 완료
- 실제 Slack 명령의 다음 공고 1건 분석과 안전한 요약 응답 검증 완료
- Slack `프로필 초안 보여줘` 명령의 라우팅과 최신 검증 초안의 항목 수 요약 구현
- Slack `프로필 검토 시작` 명령의 검증된 분석 항목 한 건 표시 구현
- 같은 Slack 스레드의 `맞아`·`제외해줘` 답변을 항목별 승인·거부 기록으로 저장
- 승인된 분석 항목을 경력·성과·기술별 비파괴 프로필 변경 제안으로 변환
- Slack `프로필 변경 검토 시작` 명령으로 첫 매핑 대기 항목과 허용 답변 표시
- 같은 Slack 스레드의 `경력 <경력ID>`·`기술수준 <숙련도>` 답변을 허용값 검증 후 불변 매핑 기록으로 저장
- Slack `프로필 최종 검토` 명령으로 모든 선택과 자동 준비 변경을 하나의 적용 전 최종 요약으로 표시
- 같은 Slack 스레드의 `최종 승인` 뒤에만 원본을 보존한 새 비공개 프로필 버전 생성
- 승인된 새 버전을 검증된 활성 프로필로 기록하고 다음 공고 발견·큐·분석에서 우선 사용
- 첨부 문서별 외부 AI 분석 범위를 안내하고 같은 Slack 스레드의 명시적 동의·거부를 불변 기록으로 저장
- 활성 프로필의 확인된 목표 직무·증거 있는 기술·명시된 선호에서 검색 계획을 자동 재생성
- 실제 TXT·Markdown·DOCX 첨부 직후 보수적인 로컬 규칙으로 원문 근거형 프로필 초안을 자동 생성

다음 단계:

1. 실제 Slack 첨부부터 개인화 공고 추천까지 전체 흐름을 검증
2. 추천에 대한 사용자 피드백을 Slack 대화에 연결
3. 공식 채용 소스를 단계적으로 확장

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
    |   |-- GREENHOUSE_BOARD_CONFIG_SCHEMA.md
    |   |-- EXECUTION_LOG_SCHEMA.md
    |   |-- MATCHING_RULES.md
    |   |-- MATCH_RESULT_SCHEMA.md
    |   `-- SLACK_INTERFACE.md
    |-- data/
    |   |-- greenhouse_boards.example.json
    |   |-- user_profile.example.json
    |   |-- job_posting.example.json
    |   |-- job_discovery.example.json
    |   |-- job_search_plan.example.json
    |   |-- job_discovery_ranking_cases.example.json
    |   |-- incruit_rss_item.example.xml
    |   |-- match_result.example.json
    |   |-- slack_interface.example.json
    |   |-- slack_app_mention.example.json
    |   `-- slack_app_manifest.example.json
    |-- src/
    |   `-- career_agent/
    |       |-- config/
    |       |   `-- greenhouse_boards.py
    |       |-- discovery/
    |       |   |-- greenhouse_board.py
    |       |   |-- incruit_feed.py
    |       |   |-- incruit_rss.py
    |       |   |-- ranking.py
    |       |   |-- report.py
    |       |   |-- service.py
    |       |   `-- store.py
    |       |-- ingestion/
    |       |   `-- greenhouse.py
    |       |-- interfaces/
    |       |   `-- slack_events.py
    |       |-- matching/
    |       |   |-- eligibility.py
    |       |   |-- experience.py
    |       |   |-- insights.py
    |       |   |-- recommendation.py
    |       |   |-- responsibility.py
    |       |   |-- service.py
    |       |   `-- technology.py
    |       |-- execution/
    |       |   `-- log.py
    |       `-- workflows/
    |           |-- greenhouse_agent.py
    |           `-- greenhouse_analysis.py
    |-- scripts/
    |   |-- analyze_greenhouse_job.py
    |   |-- check_slack_setup.py
    |   |-- discover_greenhouse.py
    |   |-- discover_incruit.py
    |   |-- list_discoveries.py
    |   |-- import_greenhouse_job.py
    |   |-- match_job.py
    |   |-- match_job_experiences.py
    |   |-- match_job_technologies.py
    |   |-- parse_slack_event.py
    |   `-- run_greenhouse_agent.py
    |-- tests/
    |   |-- test_application_recommendation.py
    |   |-- test_execution_log.py
    |   |-- test_greenhouse_board_config.py
    |   |-- test_greenhouse_agent_workflow.py
    |   |-- test_greenhouse_analysis_workflow.py
    |   |-- test_greenhouse_discovery.py
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

### docs/PROFILE_DOCUMENT_INGESTION.md

Slack 첨부 전에 이력서, 경력기술서와 포트폴리오 원본을 검증해 Git 제외 경로에 보존하는 개인정보 경계를 정의합니다.

### docs/PROFILE_EXTRACTION_SCHEMA.md

저장된 UTF-8 텍스트 문서에서 경력·프로젝트·기술·학력·희망 직무 후보를 원문 줄 근거와 함께 분리 저장하는 구조를 정의합니다.

### docs/LLM_PROFILE_ANALYSIS_PLAN.md

비공개 이력서 후보를 외부 LLM으로 보내기 전 데이터 처리 정책, 사용자 승인 경계, 구조화 JSON 계약과 모델 선택 기준을 정의합니다.

### docs/PROFILE_ANALYSIS_DRAFT_SCHEMA.md

LLM 프로필 분석 초안의 strict JSON 계약, 원본 후보 근거 검증과 사용자 승인 전 비공개 저장 구조를 정의합니다.

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

### docs/GREENHOUSE_BOARD_CONFIG_SCHEMA.md

Agent가 확인한 Greenhouse 공식 기업 채용 소스를 코드 밖에서 관리하고 여러 보드에서도 전체 상세 분석을 1건으로 제한하는 설정 구조를 정의합니다.

### docs/EXECUTION_LOG_SCHEMA.md

새 분석, 기존 분석 재사용, 무후보와 실패 실행을 프로필 및 공고 본문과 분리해 기록하는 로컬 실행 이력 구조를 정의합니다.

### docs/MATCHING_RULES.md

실제 증거의 우선순위, 일치 수준, 부족과 정보 부족의 구분 및 지원 판단 원칙을 정의합니다.

### docs/MATCH_RESULT_SCHEMA.md

공고 요구사항과 사용자 근거를 연결한 판정, 부족 역량, 추천과 지원 판단의 결과 구조를 정의합니다.

## 현재 구현 실행

핵심 분석 기능은 Python 표준 라이브러리만 사용합니다. 실제 Slack Socket Mode 연결에는 공식 Slack Bolt SDK가 필요합니다.

    python -m pip install -r requirements.txt

저장소 루트에서 다음 명령으로 테스트합니다.

    python -m unittest discover -s tests -v

실제 인크루트 RSS에서 신규 후보를 발견하고 로컬에 저장합니다.

    python scripts/discover_incruit.py

실제 발견 결과는 Git에서 제외된 `private-data/discoveries.json`에 저장됩니다. 명령 출력에는 처리 건수, 오류 건수, 신규 및 중복 건수와 우선순위 집계만 표시됩니다.

저장된 후보를 로컬 목록으로 확인합니다.

    python scripts/list_discoveries.py --limit 10

특정 발견 우선순위만 확인할 수도 있습니다.

    python scripts/list_discoveries.py --priority high --limit 10

Sendbird의 Greenhouse 공식 보드에서 현재 게시 공고 목록을 가져와 같은 로컬 저장소에 중복 없이 저장하고 프로필 관련 후보를 표시합니다.

    python scripts/discover_greenhouse.py

기본 화면에는 `high`와 `medium` 후보만 표시합니다. 제목에서 목표 직무 관련성이 확인되지 않은 `review` 후보까지 보려면 다음 명령을 사용합니다.

    python scripts/discover_greenhouse.py --include-review

목록 단계에서는 상세 본문을 가져오지 않습니다. `AI Agent`는 기존 최우선 목표인 AI Automation / Workflow Engineer에서 파생한 검색 표현이며 사용자가 별도 키워드를 입력할 필요가 없습니다. 제목에 인턴 또는 계약직이 명시되면 정규직 선호와 비교해 후보를 삭제하지 않고 우선순위만 한 단계 낮춥니다. `Expression of Interest`, `채용관심등록`, `Talent Pool`처럼 실제 모집 포지션이 아닌 제목은 발견 기록에는 `low`로 보존하되 자동 상세 분석 큐에서는 제외합니다.

공고 ID를 직접 입력하지 않고 현재 Greenhouse 목록에서 `high` 후보를 찾아 1건만 상세 분석합니다.

    python scripts/run_greenhouse_agent.py

현재 목록의 `high` 후보 중 가장 최근 공고만 분석하며 `high`가 없으면 상세 조회 없이 종료합니다. 로컬에 남은 과거 공고는 현재 목록에 없으면 선택하지 않고, 실패 시 다른 후보를 연쇄 조회하지 않습니다. 새 분석은 고유한 분석 ID를 사용해 `private-data/agent-runs/`에 저장됩니다. 같은 공고의 갱신 시각, 프로필 내용, 매칭 규칙과 분석 파이프라인 버전이 모두 같으면 기존 파일을 재사용하고 새 파일을 만들지 않습니다.

기본 실행은 `data/greenhouse_boards.example.json`의 검증된 Sendbird 소스를 읽습니다. 개인 설정은 `private-data/greenhouse_boards.json`에 두고 다음처럼 지정할 수 있습니다.

    python scripts/run_greenhouse_agent.py --board-config private-data/greenhouse_boards.json

활성 보드는 개인용 MVP에서 최대 10개까지 허용합니다. 여러 보드를 활성화해도 목록만 먼저 조회한 뒤 모든 현재 `high` 후보 중 가장 최근 1건만 상세 분석합니다. 일부 보드가 실패하면 실패 보드를 표시하고 나머지를 계속 처리하며, 모든 보드가 실패하면 상세 분석 없이 종료합니다. 이 등록부는 직무 키워드 입력이 아니라 Agent가 확인한 공식 채용 소스를 관리하기 위한 것입니다.

모든 실행은 `private-data/execution-runs/`에 별도 이력으로 저장됩니다. 기존 분석을 재사용하거나 현재 `high` 후보가 없는 경우도 기록하며 실패 실행은 오류 상태를 남깁니다. 이 이력에는 사용자 프로필과 채용공고 본문을 복제하지 않습니다.

최근 Agent 실행의 현재 목록에서 실제 검토 후보를 최대 10건까지 자동으로 정렬합니다.

    python scripts/build_greenhouse_review_queue.py

로컬 2개 보드 설정으로 목록을 먼저 갱신하려면 다음 두 명령을 순서대로 실행합니다.

    python scripts/run_greenhouse_agent.py --board-config private-data/greenhouse_boards.json
    python scripts/build_greenhouse_review_queue.py

검토 큐는 `private-data/review-queues/`에 새 파일로 저장됩니다. `high`, `medium` 다음에 프로필 생성 직무 표현과 부분적으로 가까운 `review` 후보를 배치합니다. `review` 후보는 같은 목표 직무 축에서 구별 가능한 단어 조합이 있거나 `ITSM`, `FinOps`처럼 그 자체로 고유한 표현이 있어야 합니다. `Engineer`, `엔지니어`처럼 일반적인 직무 단어만 같은 후보와 과거 발견 기록의 채용관심등록·인재풀 제목은 제외합니다. 큐 생성은 추가 상세 조회를 하지 않으며 각 후보가 최신 규칙으로 이미 분석됐는지만 표시합니다.

검토 큐에서 프로필의 지역·고용 조건과 명백히 충돌하지 않는 첫 미분석 공고 1건만 상세 분석합니다.

    python scripts/analyze_next_greenhouse_review.py

명령을 한 번 실행할 때 공식 Greenhouse 상세 API 요청도 최대 1건입니다. 분석 파일과 실행 이력을 저장하고, 원본 큐를 덮어쓰지 않은 새 큐에서 해당 후보를 `analyzed_current`로 연결합니다. 프로필이나 분석 규칙이 바뀐 오래된 큐는 사용하지 않습니다. 사용자 검토 상태는 자동으로 완료하지 않으며, 필수 조건 또는 주요 업무 추출 결과가 0개이면 콘솔에 구조화 품질 경고를 표시합니다.

이력서, 경력기술서 또는 포트폴리오 파일 1개를 비공개 원본 저장소에 가져옵니다.

    python scripts/import_profile_document.py --file "C:\path\resume.pdf" --kind resume

가져오기 명령은 `.txt`, `.md`, `.pdf`, `.docx`를 최대 10MB까지 허용합니다. 파일 형식과 내용 해시를 확인하고 `private-data/profile-documents/`에 저장하며, 동일한 종류와 내용은 다시 쓰지 않습니다. 이 명령 자체는 문서 본문을 해석하거나 사용자 프로필을 갱신하지 않습니다.

저장된 UTF-8 TXT 또는 Markdown 문서에서 검토용 프로필 후보를 추출합니다. 문서 ID는 앞의 가져오기 명령 출력에서 확인합니다.

    python scripts/extract_profile_text.py --document-id profile-document-resume-example

인식된 경력·프로젝트·기술·학력·희망 직무·업무 선호 제목 아래의 문장만 후보로 만들고 원문 줄 번호를 연결합니다. 연락처 형태의 줄은 제외하며 모든 후보는 `needs_review`로 저장됩니다. 결과는 `private-data/profile-extractions/`에만 저장하고 실제 사용자 프로필은 변경하지 않습니다.

추출 후보 한 건에 사용자의 승인 또는 거부를 기록합니다. 추출 결과 ID와 후보 ID는 추출 JSON에서 확인합니다.

    python scripts/review_profile_candidate.py --extraction-id profile-text-extraction-example --candidate-id candidate-001 --decision approve

`approve`는 승인, `reject`는 거부입니다. 결과는 `private-data/profile-candidate-reviews/`에 새 파일로 저장되며 후보 문장을 다시 복제하지 않습니다. 이 명령도 실제 사용자 프로필을 변경하지 않습니다.

같은 후보의 가장 최근 결정 중 승인된 항목만 프로필 갱신안으로 모읍니다.

    python scripts/build_profile_update_proposal.py --extraction-id profile-text-extraction-example

갱신안은 기준 프로필의 SHA-256 지문, 원문 줄 근거와 승인 기록을 연결하고 `private-data/profile-update-proposals/`에 저장됩니다. 승인된 후보가 없으면 `no_approved_candidates` 상태와 개수만 기록합니다. 승인 문장을 아직 기존 프로필의 세부 객체로 변환하거나 실제 프로필 파일에 적용하지 않습니다.

승인된 기술 후보를 기존 프로필의 기술 목록과 비교합니다. 갱신안 ID는 앞 명령의 저장 파일명에서 확인합니다.

    python scripts/build_profile_skill_mapping.py --proposal-id profile-update-proposal-example

기존 기술과 대소문자·공백을 제외하고 같은 이름이면 중복으로 연결합니다. 새 기술명은 숙련도와 사용 증거가 없으므로 `needs_details`, 여러 기술이 한 줄에 섞였을 수 있으면 `needs_separation`으로 남깁니다. 결과는 `private-data/profile-skill-mappings/`에 저장되며 완성된 기술 객체나 숙련도를 자동 생성하지 않습니다.

`needs_details` 기술 후보에 사용자가 확인한 숙련도와 실제 사용 증거를 기록합니다. 기술 매핑 ID와 항목 ID는 앞 명령의 결과 JSON에서 확인합니다.

    python scripts/confirm_profile_skill.py --mapping-id profile-skill-mapping-example --mapping-item-id skill-mapping-item-001 --level project --evidence "Tech News Automation에서 사용"

증거가 여러 개면 `--evidence`를 반복합니다. 결과는 `private-data/profile-skill-confirmations/`에 불변 파일로 저장되고 후보 기술명을 자동 복제하지 않습니다. 이 명령도 사용자 프로필을 변경하지 않습니다.

기술 후보별 가장 최근 사용자 확인을 선택해 완성된 기술 추가안을 만듭니다.

    python scripts/build_profile_skill_additions.py --mapping-id profile-skill-mapping-example

최신 확인이 있는 `needs_details` 후보만 `skill_id`, `name`, `level`, `evidence`를 갖춘 제안으로 만듭니다. 결과는 `private-data/profile-skill-additions/`에 저장되며 상태는 `needs_final_review`입니다. 현재 프로필 지문이 달라졌거나 기존 기술과 중복되면 거부하고, 실제 프로필 파일은 수정하지 않습니다.

완성된 기술 추가안 한 건의 최종 승인 또는 거부를 기록합니다.

    python scripts/review_profile_skill_addition.py --proposal-id profile-skill-addition-example --addition-item-id skill-addition-item-001 --decision approve

결과는 `private-data/profile-skill-addition-reviews/`에 불변 파일로 저장됩니다. 검토 기록에는 기술명, 숙련도와 사용 증거를 자동 복제하지 않으며 추가안 ID와 항목 ID만 연결합니다. 이 명령도 사용자 프로필을 변경하지 않습니다.

추가 항목별 가장 최근 최종 판단을 선택하고 승인된 기술만 새 프로필 버전에 적용합니다.

    python scripts/apply_profile_skill_additions.py --proposal-id profile-skill-addition-example

적용 직전에 기준 프로필 ID와 전체 내용 SHA-256, 기존 기술명과 `skill_id` 중복을 다시 확인합니다. 결과는 `private-data/profile-applications/<application-id>/`에 저장합니다. 승인 기술이 있으면 `application.json`과 `profile.json`을 함께 만들고, 승인 기술이 없으면 적용 이력만 만들며 새 프로필은 생성하지 않습니다. 기준 프로필 원본은 항상 보존합니다.

첫 Slack 채널 호출 형식을 합성 이벤트로 검증합니다.

    python scripts/parse_slack_event.py

예제의 `<@봇사용자ID> 다음 공고 찾아줘` 문장을 기존 다음 공고 분석 동작명으로 변환합니다. 워크스페이스, 앱, 허용 사용자와 허용 채널을 검사하고 `event_id`가 같은 재전송은 기존 요청을 재사용합니다. 현재는 로컬 입력 경계만 검증하므로 실제 Slack 접속과 공고 분석은 실행하지 않습니다. 세부 계약은 `docs/SLACK_INTERFACE.md`에 기록했습니다.

Slack 앱 생성 전에는 `data/slack_app_manifest.example.json`을 사용합니다. 실제 앱을 설치한 뒤 `.env.example`을 `.env`로 복사해 App Token과 Bot Token을 본인 PC에서만 입력합니다. `python scripts/verify_slack_tokens.py`로 인증한 뒤, 출력된 인증 결과 ID와 Slack 화면의 App ID, 본인 User ID, 테스트 Channel ID로 Git 제외 설정을 생성합니다.

    python scripts/configure_slack_interface.py --auth-id slack-auth-인증결과ID --app-id A앱ID --user-id U사용자ID --channel-id C채널ID

이 명령은 검증된 워크스페이스·봇 정보와 개인 허용 목록을 `private-data/slack_interface.json`에 저장하며 실제 ID 값은 다시 출력하지 않습니다. 준비 상태는 다음 명령으로 검사합니다.

    python scripts/check_slack_setup.py

검사 명령은 Token 값을 출력하거나 Slack에 접속하지 않습니다. 2026-09-14 실제 개인 설정은 이 준비 검사를 통과했습니다.

Token을 입력한 뒤 실제 인증과 Socket Mode 사용 가능 여부만 확인합니다.

    python scripts/verify_slack_tokens.py

이 명령은 Slack 공식 `auth.test`와 `apps.connections.open`만 호출합니다. Token과 임시 WebSocket URL은 결과 파일이나 콘솔에 남기지 않고, 비밀정보가 없는 인증 상태와 Slack 식별자만 `private-data/slack-auth/`에 저장합니다.

실제 Slack 수신기를 시작합니다.

    python scripts/run_slack_socket.py

실행 중 지정 채널에서 `@career_break 다음 공고 찾아줘`를 보내면 허용된 사용자와 채널의 이벤트만 저장하고, 분석 시작을 먼저 알린 뒤 검토 큐의 다음 공고 1건을 분석합니다. 큐가 비면 Greenhouse 공식 보드 목록을 한 번 갱신하고 새 큐에서 다시 검사합니다. 이 목록 갱신은 상세 공고를 분석하지 않습니다. 성공 시 회사·공고명과 원문 링크, 공고 정보 충분도, `RECOMMEND`·`HOLD`·`NOT_RECOMMEND` 추천 상태와 근거를 원래 메시지 스레드에 요약합니다. 확인된 일치, 확인된 부족 또는 불일치, 공고에서 확인할 수 없는 정보와 비교를 위해 추가 확인할 정보를 구분합니다. 조건에 맞는 새 공고가 없으면 실패가 아닌 정상 빈 결과를 전달하며 분석 완료, 조건 불일치와 현재 분석 가능 개수를 구분합니다. 같은 `event_id` 재전송에는 분석과 답변을 중복 실행하지 않습니다. 종료는 `Ctrl+C`입니다.

정확한 기존 명령이 아니어도 `내 경력에 맞는 새 공고 하나 찾아줘`, `AI Agent Engineer와 QA 자동화 공고를 찾아줘`, `지금 프로필 분석 결과를 요약해줘`처럼 자연어로 요청할 수 있습니다. 지원되지 않은 자연어만 Gemini planner가 일시적으로 해석하며 메시지 원문은 로컬 요청 파일과 로그에 저장하지 않습니다. 모델은 공고 찾기, 검증된 첨부 분석, 프로필 요약, 프로필 검토 시작 중 1~3개만 선택할 수 있습니다. 공고 요청에 사용자가 명시한 직무는 최대 3개의 일회성 검색 초점으로만 전달되며, URL·경로·Slack ID·Token·명령 구문과 프롬프트 주입 문구는 로컬에서 거부합니다. 승인·거부와 최종 프로필 반영은 모델이 선택할 수 없습니다. 모델의 계획은 로컬 strict validator를 통과한 뒤 기존 내부 기능으로 실행되며 Slack 답변도 모델 자유문이 아니라 기존 검증 포맷터가 만듭니다. 동일 `event_id` 재전송은 planner와 도구를 다시 실행하지 않습니다.

`@career_break 프로필 초안 보여줘`를 보내면 비공개 저장소에서 가장 최근 검증된 문서 추출 결과와 그 추출 결과에 속한 최신 `needs_review` 분석 초안을 다시 검증합니다. Slack에는 경력·성과·기술 근거와 추가 질문의 개수만 표시하며 이력서 원문, 내부 ID, 공급자와 로컬 경로는 표시하지 않습니다. 초안이 없으면 문단 분류까지만 완료됐다고 정확히 안내하며 분석 결과를 임의로 생성하지 않습니다. 현재 개인용 MVP는 허용 사용자 1명을 전제로 최신 추출 결과를 선택합니다.

`@career_break 프로필 검토 시작`을 보내면 최신 검증 초안의 경력·성과·기술·추가 질문 중 아직 검토하지 않은 항목 한 건을 같은 스레드에 표시합니다. Slack 제어 문자열을 무해화하고 후보 ID, 초안 ID, 공급자와 로컬 경로는 숨깁니다. 표시된 스레드에서 `@career_break 맞아`라고 답하면 승인, `@career_break 제외해줘`라고 답하면 제외 결정을 비공개 불변 기록으로 저장합니다. 다른 사용자·채널·스레드의 답변과 스레드 밖 답변은 해당 항목에 연결하지 않습니다. 결정 후 다음 `프로필 검토 시작`은 이미 검토한 항목을 건너뜁니다. 이 결정만으로 개인 프로필이나 공고 검색 조건을 변경하지 않습니다. 실제 사용자 문서에 연결된 분석 초안이 없으면 아직 분석 초안이 없다고 안내합니다.

모든 분석 항목 검토를 마친 뒤 `@career_break 프로필 변경 검토 시작`을 보내면 최신 결정을 사용해 비파괴 변경 제안을 만들고 첫 매핑 대기 항목을 표시합니다. 경력·성과에는 연결 가능한 기존 경력 ID를 보여주고, 새 기술에는 허용된 숙련도 값을 보여줍니다. 표시된 같은 스레드에서 `@career_break 경력 career-001` 또는 `@career_break 기술수준 project`처럼 답하면 현재 프로필과 세션의 허용값을 다시 검증해 비공개 불변 기록으로 저장합니다. 다른 사용자·채널·스레드의 답과 허용되지 않은 값은 연결하지 않으며, 다음 `프로필 변경 검토 시작`은 이미 선택한 항목을 건너뜁니다. 아직 실제 프로필을 변경하지 않습니다.

모든 매핑 선택을 마친 뒤 `@career_break 프로필 최종 검토`를 보내면 경력 수행 근거, 성과 근거, 기존 기술 근거와 새 기술 추가를 하나의 불변 최종 변경안으로 합쳐 같은 스레드에 표시합니다. 기준 프로필이 달라졌거나 선택이 빠졌으면 최종 변경안을 만들지 않습니다. 내부 제안·검토 ID는 공개하지 않고 실제 적용 전 변경 개수, 대상 경력·기술과 근거 요약만 보여줍니다. 표시된 같은 스레드에서 `@career_break 최종 승인`이라고 답하면 명시적 승인 기록을 저장하고 원본과 분리된 새 비공개 프로필 버전을 생성합니다. `@career_break 최종 취소`는 거부 이력만 남기고 프로필 버전을 만들지 않습니다. 다른 사용자·채널·스레드의 답변과 이미 결정된 세션은 연결하지 않습니다.

승인으로 생성된 새 프로필 버전은 내용 지문과 적용 ID만 담은 별도 불변 활성화 기록으로 연결됩니다. 다음 `다음 공고 찾아줘` 실행의 공식 소스 갱신, 검토 큐 재생성과 상세 공고 분석은 명시적 `--profile` 입력이 없을 때 최신 활성 프로필을 우선 사용합니다. 활성화 기록, 적용 기록 또는 프로필 지문이 서로 다르면 공개 예제로 조용히 되돌아가지 않고 실행을 중단합니다.

공고 발견·검토 큐·상세 분석 스크립트는 명시적 `--search-plan` 입력이 없으면 선택된 활성 프로필에서 검색 계획을 즉시 다시 만듭니다. 목표 직무 원문과 검토된 직무 ID별 통제 동의어, 실제 근거가 있는 `basic`·`project`·`work` 기술, 프로필에 명시된 지역·고용 형태와 업무 선호만 사용합니다. `exposure`·`learning` 기술, 경력 연수와 재택 선호는 검색 신호로 추정하지 않습니다. 낮은 선호는 강제 제외가 아니라 순위 하향에만 사용합니다. 명시적 계획도 선택 프로필의 ID와 내용 지문이 정확히 같아야 하며, 다음 상세 분석은 검토 큐가 현재 계획과 같은 ID 및 의미 내용 지문으로 만들어진 경우에만 진행합니다.

`@career_break 프로필 분석해줘` 또는 같은 의미의 자연어와 함께 `.txt`, `.md`, `.pdf`, `.docx` 파일 1개를 첨부하거나 봇 호출과 파일만 보내면 파일 ID·형식·크기를 검증합니다. `files:read` 권한이 승인된 실제 수신기는 `files.info`로 파일 정보를 다시 확인하고 인증된 Slack 비공개 URL에서만 내려받아 `private-data/profile-documents/`에 저장합니다. TXT·Markdown·DOCX는 저장 직후 로컬 추출기를 실행하고 Slack에는 경력·프로젝트·기술 등 섹션별 검토 후보 개수와 기간, 수치, 실행·개선, 통제된 기술명 언급의 근거 신호 개수를 답변합니다. 이어 기간과 행동이 함께 있는 경력, 수치와 결과 표현이 함께 있는 성과, 기술명과 사용 행동이 함께 있는 기술만 보수적으로 초안에 올리고 나머지는 확인 질문으로 남깁니다. 초안은 외부 네트워크를 사용하지 않으며 원문에 실제 존재하는 근거만 허용하고 기술 숙련도는 미확정으로 고정합니다. Slack에는 초안 항목 수와 다음 검토 명령만 표시합니다. PDF는 현재 비공개 저장까지만 지원하며 본문 추출 미지원 상태를 구분해 알립니다. 모든 후보와 근거 신호는 사용자 확인 전까지 개인 프로필에 반영하지 않습니다.

Slack 수신기는 문서별 외부 AI 분석 동의 세션을 만들 수 있습니다. 사용자가 같은 스레드에서 명시적으로 승인하면 추출 결과 ID, 최소 요청의 SHA-256 지문, Gemini 모델, Slack 사용자·채널·스레드와 최신 승인 기록을 다시 검증한 뒤 후보 문장만 Gemini 무료 API로 전송합니다. 파일명, 문서 ID, 로컬 경로와 연락처 형태는 보내지 않습니다. Gemini 결과는 원문 구간 검증을 통과한 경우에만 비공개 `needs_review` 초안으로 저장하며 개인 프로필과 검색 조건은 자동 변경하지 않습니다. 거부, 미결정, 다른 문서·모델·스레드의 승인은 재사용하지 않습니다.

로컬 합성 LLM 응답으로 프로필 분석 초안 계약을 확인합니다. 실제 네트워크 요청은 발생하지 않습니다.

    python scripts/build_profile_analysis_draft.py --extraction-id profile-text-extraction-example --response-file data/profile_analysis_response.example.json

합성 응답의 모든 사실 표현은 참조 후보 문장에 포함된 원문 구간이어야 합니다. 결과는 `private-data/profile-analysis-drafts/`에 `needs_review` 상태로 저장되며 사용자 프로필은 변경하지 않습니다. 예제 응답은 `data/profile_document.example.md`에서 만든 추출 결과와 함께 사용합니다.

실제 OpenAI API 분석 명령도 구현되어 있지만 외부 전송 승인 없이는 실행 전에 중단됩니다. `.env`의 `OPENAI_API_KEY`와 명시적 `--approve-external-transfer`가 모두 있어야 연락처 형태를 제외한 후보 문장만 전송합니다. 파일, 문서 ID, 추출 ID와 로컬 경로는 보내지 않으며 Responses API 요청은 `store: false`, strict JSON Schema, 도구 없음, 기본 모델 `gpt-5.6-luna`, reasoning effort `low`로 고정합니다.

    python scripts/build_openai_profile_analysis_draft.py `
      --extraction-id profile-text-extraction-실제ID `
      --approve-external-transfer

이 플래그는 후보 문장이 OpenAI API로 전송되고 API 사용료가 발생할 수 있다는 점을 사용자가 확인했다는 의미입니다. API 응답은 기존 원문 근거 검증을 다시 통과해야만 비공개 `needs_review` 초안으로 저장됩니다. 현재 실제 사용자 문서로는 실행하지 않았습니다.

Gemini 무료 API는 기능 개발 테스트에만 사용합니다. 공개 합성 문서는 다음 명령으로 분석합니다.

    python scripts/build_gemini_synthetic_profile_analysis_draft.py `
      --confirm-public-synthetic-data

기본 모델은 `gemini-3.5-flash-lite`, 추론 수준은 `low`, 응답 형식은 JSON Schema, 도구 사용은 없음으로 고정합니다. 공개 합성 경로는 기존 고정 fixture 지문 제한을 유지합니다. 실제 사용자 문서는 정확한 Slack 승인 기록이 있을 때만 다음 명령으로 분석할 수 있습니다.

    python scripts/run_consented_gemini_profile_analysis.py

이 명령은 최신 추출 결과와 정확히 일치하는 최신 승인을 먼저 검증하며, 결과는 `private-data/profile-analysis-drafts/`에 저장합니다. Gemini가 거부하는 일부 스키마 제약은 공급자 요청에서만 제거하고 더 엄격한 원문 근거·항목 수 검증은 로컬에서 다시 수행합니다.

Gemini 무료 등급의 입력과 응답은 Google 제품·모델 개선과 사람 검토에 사용될 수 있습니다. 따라서 기본값은 외부 전송 금지이며, 현재 개인용 개발 테스트에서는 사용자가 이 조건을 이해하고 해당 문서 전송을 명시적으로 승인한 경우에만 실행합니다. 실제 서비스 전환 시에는 공급자, 유료 데이터 처리 조건, 보존 정책과 동의 화면을 다시 결정해야 합니다. 근거는 [Gemini API 추가 이용약관](https://ai.google.dev/gemini-api/terms), [오용 감시 정책](https://ai.google.dev/gemini-api/docs/usage-policies), [Zero data retention 안내](https://ai.google.dev/gemini-api/docs/zdr)입니다.

검증된 프로필 분석 초안의 항목 한 건에 대한 사용자 결정을 별도 기록할 수 있습니다. 항목 순번은 1부터 시작하며 결정은 `approve` 또는 `reject`입니다.

    python scripts/review_profile_analysis_item.py `
      --draft-id profile-analysis-draft-실제ID `
      --item-type career_evidence `
      --item-position 1 `
      --decision approve

결과는 `private-data/profile-analysis-reviews/`에 저장됩니다. 분석 문장과 후보 원문을 검토 기록에 복제하지 않으며, 이 결정만으로 개인 프로필이나 검색 조건을 변경하지 않습니다. 실제 Slack에서는 `프로필 검토 시작`으로 표시된 같은 스레드의 `맞아`와 `제외해줘` 답변이 이 기록 경계를 사용합니다.

같은 분석 항목에 결정이 여러 번 있으면 최신 결정만 선택해 비파괴 프로필 변경 제안을 만듭니다.

    python scripts/build_profile_analysis_update_proposal.py `
      --draft-id profile-analysis-draft-실제ID

경력과 성과는 기존 경력을 자동 추정하지 않고 경력 선택 대기로 둡니다. 기존 기술과 이름이 정확히 같은 기술 근거는 숙련도 변경 없이 근거 추가로 제안하고, 새 기술은 숙련도 확인 대기로 둡니다. 추가 확인 질문과 기존 프로필의 중복 기술 근거는 변경에서 제외합니다. 결과는 `private-data/profile-analysis-update-proposals/`에 저장되며 기준 프로필은 변경하지 않습니다.

상세 분석된 공고에 사용자의 실제 판단을 별도 기록합니다. `fit`은 적합, `hold`는 보류, `not_fit`은 부적합입니다.

    python scripts/record_greenhouse_review.py --position 1 --fit hold --recommendation-useful yes --notes "직무는 관련 있지만 경력 조건 확인 필요"

결과는 Git에서 제외된 `private-data/human-reviews/`에 새 파일로 저장됩니다. 프로필 원문과 공고 본문을 복제하지 않으며 원본 검토 큐도 변경하지 않습니다. 이 명령은 향후 Slack의 버튼이나 사용자 답변을 연결할 내부 입력 경계입니다. 이후 검토 큐를 생성하거나 다음 공고를 분석하면 같은 공고와 같은 분석 ID의 가장 최근 사용자 판단이 새 큐에 병합됩니다. 피드백은 아직 후보 검색 순위를 자동 변경하지 않습니다.

예제 사용자 프로필과 예제 공고의 기술 요구사항만 비교합니다.

    python scripts/match_job_technologies.py

다른 구조화된 입력 파일은 `--profile`과 `--posting`으로 지정할 수 있습니다. 현재 이 명령은 `skill`과 `cloud` 유형만 평가하며 업무 경험, 지원 조건과 최종 지원 추천은 아직 만들지 않습니다.

예제 공고의 경험 요구사항을 프로젝트와 행동 증거에 연결합니다.

    python scripts/match_job_experiences.py

이 명령은 현재 REST API 연동, 자동화 프로젝트와 소프트웨어 엔지니어링 경험을 판정합니다. 복합 경험 조건은 경력에서 확인되는 부분만 `partial`로 연결하고, 경력 연수와 직접 소유 범위는 별도 확인 대상으로 남깁니다. 해석 규칙이 없는 경험은 부족으로 단정하지 않고 `unknown`으로 유지합니다.

기술과 경험 판정을 공고의 원래 순서로 합쳐 확인합니다.

    python scripts/match_job.py

통합 명령은 아직 평가하지 못하는 조건도 결과에서 누락하지 않고 `unknown`으로 표시합니다. 필수·우대 조건, 주요 업무, 경력·학력·지역·고용 형태, 지원 강점·부족·미확인 항목과 근거 기반 지원 추천을 출력합니다. 추천은 합격 확률이 아니라 현재 프로필과 공고의 비교 결과입니다.

Greenhouse를 사용하는 기업의 공개 상세공고 1건을 자동으로 구조화합니다. board token과 job ID는 해당 기업의 공개 채용 URL 또는 API에서 확인한 값을 사용합니다.

공고 조회, 구조화, 프로필 비교와 분석 JSON 저장을 한 번에 실행합니다.

    python scripts/analyze_greenhouse_job.py --board sendbird --job-id 8395379002

결과는 기본적으로 `private-data/analysis-greenhouse-<board>-<job-id>.json`에 저장됩니다. 분석 ID, 생성 시각, 입력 공고 URL, 요구사항별 판정, 강점·부족·미확인 항목과 지원 판단이 포함됩니다. 사용자 프로필 원문은 결과에 복제하지 않으며 사용자 검토 전 상태는 `not_reviewed`입니다. 콘솔에는 지원 판단에 영향이 큰 미확인 항목 5개만 먼저 표시하고 전체 목록은 JSON에 보존합니다.

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
- 웹개발·서버 운영 경력을 복합 소프트웨어 엔지니어링 조건의 부분 근거로 연결하고 요구 연수 미추정
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
- 미확인 항목을 필수 조건·지원 가능 조건·주요 업무·우대 조건 순으로 정렬하고 콘솔에는 상위 5개만 표시
- Greenhouse 보드 목록을 본문 없이 조회하고 프로필에서 도출한 `AI Agent` 표현으로 후보 선별
- `Seoul`과 서울을 같은 지역으로 처리하고 명시된 인턴·계약직은 정규직 선호 기준으로 순위만 낮춤
- Greenhouse 목록을 같은 로컬 저장소에 합치고 기업 보드와 외부 ID 기준으로 중복 제거
- 현재 Greenhouse 목록에 있는 가장 최근 `high` 후보 1건만 상세 분석
- 현재 `high` 후보가 없거나 로컬 저장소에만 남은 과거 `high` 후보뿐이면 상세 분석 없이 종료
- 현재 조회 결과를 저장된 과거 순위 대신 다시 계산된 프로필 관련성으로 선택
- 공고·프로필·규칙이 모두 같을 때 기존 분석을 재사용하고 프로필이 달라지면 새 분석 실행
- Greenhouse 소스 등록부의 필수 필드, HTTPS URL, 중복 token과 활성 보드 1~10개 제한 검증
- 여러 Greenhouse 보드의 시간대가 다른 게시 시각을 실제 시각으로 비교하고 전역 상세 분석 1건만 실행
- 일부 보드 목록 실패 시 나머지 후보를 처리하고 모든 보드 실패 시 상세 분석 없이 종료
- 성공, 재사용, 무후보와 실패 실행을 별도 파일로 보존하고 공고 본문과 프로필 원문 제외
- 미확인 사실을 부족으로 간주하지 않고 확인된 기술 부족만 학습 추천 대상으로 사용
- 한 번에 학습 과제 1개만 제안하며 완료 프로젝트에 적용할 코드·설정, 실행 문서와 재현 성공 로그를 완료 증거로 요구
- 우대사항인 클라우드 기술은 여러 실제 공고의 반복 수요를 측정하기 전까지 자동 학습 과제로 만들지 않음
- 학습 과제나 직접 증거가 있는 약한 업무 판정을 기존 완료 프로젝트의 개선점과 연결
- 포트폴리오 개선도 최대 1개로 제한하고 변경 코드, 실행 방법과 실제 동작 로그를 기대 증거로 요구
- 정보가 없는 업무와 계획 중인 프로젝트를 포트폴리오 개선 근거로 사용하지 않음
- 최신 Greenhouse 목록에서 `high`, `medium`과 근거 있는 `review` 후보를 합쳐 검토 큐를 최대 10건 생성
- 일반적인 `Engineer` 한 단어 또는 영문·한글 번역 중복만 일치하는 `review` 후보는 자동 상세 분석 큐에서 제외
- 채용관심등록·인재풀처럼 실제 모집 포지션이 아닌 명시적 제목은 기록에 보존하고 자동 상세 분석 큐에서 제외
- 같은 우선순위에서는 지역·고용 형태와 Agent 생성 직무 표현의 넓은 단어 일치를 사용해 정렬
- 프로필, 공고 갱신 시각과 규칙 버전이 같은 상세 분석 여부를 큐에서 구분
- 검토 큐에 사용자 프로필과 공고 본문을 복제하지 않고 사용자 검토 상태를 `not_reviewed`로 유지
- 검토 큐에서 명백한 지역·고용 불일치가 없는 첫 `needs_analysis` 후보 1건만 공식 상세 API로 분석
- 상세 분석, 실행 이력과 후속 큐를 각각 새 파일로 저장하고 분석 ID를 큐에 연결
- 프로필 지문 또는 규칙 버전이 다른 오래된 큐를 거부하고 빈 필수 조건·주요 업무 추출을 경고
- Greenhouse의 `What You Will Do` 업무 섹션과 여러 직급이 묶인 `Basic Qualifications`에서 첫 직급 조건만 보수적으로 구조화
- 상세 분석된 공고의 사용자 적합·보류·부적합 판단을 비공개 불변 피드백 파일로 기록
- 같은 공고와 현재 분석 ID에 연결된 가장 최근 사용자 판단을 후속 검토 큐에 자동 병합
- 기술 추가 항목별 최신 최종 판단 선택과 승인 기술의 비파괴 새 프로필 버전 적용
- 오래된 기준 프로필, 변조된 최종 검토 참조와 기술명·`skill_id` 중복 적용 거부
- 승인 기술이 없을 때 적용 이력만 저장하고 빈 새 프로필 생성을 방지
- Slack `app_mention`의 워크스페이스·앱·사용자·채널 허용 목록 검증
- 지원하지 않는 명령, 봇 메시지와 메시지 하위 유형을 실제 동작으로 연결하지 않음
- 같은 Slack `event_id` 재전송을 한 요청으로 재사용하고 원문 메시지를 저장하지 않음
- 조건에 맞는 새 공고가 없으면 상세 조회 없이 정상 빈 결과와 현재 큐 상태를 Slack에 응답
- Slack 첨부파일 1개의 ID·형식·크기를 검증하고 내용과 다운로드 URL 없이 비공개 요청으로 저장
- `files.info` 재검증, 외부 리디렉션 차단과 인증 다운로드를 거쳐 Slack 첨부파일을 기존 비공개 문서 저장소에 저장

현재 구현은 공식 인크루트 RSS와 설정에 등록된 Greenhouse 기업 보드 목록을 읽고 로컬 JSON에 신규 후보를 중복 없이 저장합니다. Greenhouse 후보는 활성 프로필에서 자동 생성한 목표 직무와 선호 조건으로 정렬하며, 여러 보드 전체의 현재 후보 중 한 번에 1건을 공고 ID 입력이나 복사·붙여넣기 없이 상세 조회·분석·저장합니다. 조건에 맞는 새 후보가 없으면 무관한 공고를 분석하지 않고 정상 빈 결과를 반환합니다. 사용자 문서 원본을 검증해 비공개 저장하고 UTF-8 텍스트·Markdown·DOCX에서 검토용 프로필 후보와 로컬 검증 초안을 만듭니다. 문서별 명시적 Slack 승인 후에는 최소 후보 텍스트만 Gemini 무료 API로 분석하고, strict JSON 및 원문 근거 검증을 통과한 비공개 초안만 저장할 수 있습니다. 이 초안은 자동으로 개인 프로필에 반영되지 않습니다. 승인된 프로필 버전은 다음 공식 공고 발견, 검토 큐와 상세 분석의 활성 프로필로 사용되고 검색 계획도 같은 프로필에서 자동 재생성됩니다. 현재 궁극적인 개인용 MVP 진행률은 약 92%입니다. 아직 고정 명령 중심 Slack 흐름을 자연어 도구 선택형 Agent로 전환하는 작업, 실제 Slack 전체 재검증, PDF 본문 추출과 채용 소스 확대가 남아 있습니다.

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

현재 상태: 사용자 문서 비공개 수신과 로컬 검증 초안, 승인 기반 프로필 활성화, 자동 공고 발견·선별, 검토 큐와 공식 ATS 상세 분석, 근거 기반 추천, Slack Socket Mode 수신기 구현

공식 인크루트 RSS와 설정에 등록된 Greenhouse 기업 보드 목록을 중복 없이 저장하고, 활성 프로필에서 자동 생성한 검색 계획으로 후보를 선별해 한 번에 1건씩 상세 분석합니다. TXT·Markdown·DOCX 첨부는 비공개 저장 후 외부 전송 없이 검토용 프로필 초안을 자동 생성하며, Slack에서 항목 승인·제외, 경력·숙련도 매핑과 최종 승인을 거쳐 원본과 분리된 새 프로필 버전으로 활성화할 수 있습니다. Slack 상세 응답에는 공고 원문 링크, 판단 근거, 강점 증거와 우선 확인 질문을 포함합니다. 다음 기능 단계는 실제 첨부부터 개인화 공고 추천까지 Slack 전체 흐름을 다시 확인하는 것입니다.
