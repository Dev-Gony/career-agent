# Career Agent

개인의 경력, 프로젝트, 기술 역량을 실제 채용공고와 비교해  
**확인된 강점, 부족한 역량, 추가 확인이 필요한 정보, 지원 판단 근거**를 정리하는 개인용 커리어 분석 시스템입니다.

단순히 "몇 % 적합" 같은 점수를 만드는 것보다, **왜 그렇게 판단했는지 설명 가능한 결과**를 만드는 데 초점을 맞추고 있습니다.

## Problem

취업 준비를 하면서 반복적으로 생기는 문제를 자동화하고 싶었습니다.

- 채용공고마다 요구사항을 다시 읽고 내 경험과 비교해야 함
- 경력, 프로젝트, 기술 정보가 여러 문서에 흩어져 있음
- 부족한 역량과 단순 정보 부족을 구분하기 어려움
- 부족한 기술을 발견해도 무엇부터 보완해야 할지 결정하기 어려움
- 추천 결과가 실제 경험이 아니라 막연한 키워드 일치에 의존하기 쉬움

Career Agent는 이 과정을 **구조화된 데이터와 근거 기반 규칙**으로 반복 가능하게 만드는 프로젝트입니다.

## Current Flow

```text
Slack / Profile Document
        |
        v
Private Profile Data
        |
        v
Job Discovery
(RSS / Greenhouse)
        |
        v
Job Posting Normalization
        |
        v
Requirement Matching
        |
        +--> confirmed match
        +--> confirmed gap
        +--> unknown
        |
        v
Learning / Portfolio Suggestions
        |
        v
Slack Thread Response
```

## What Is Implemented

### Job discovery

- 인크루트 RSS 기반 신규 공고 발견
- Greenhouse 공개 Job Board API 연동
- 여러 기업 보드에서 후보 수집
- 실행 간 중복 제거
- 프로필 기반 후보 우선순위 정렬
- 한 번의 실행에서 상세 분석 대상을 제한해 불필요한 요청 방지

### Evidence-based matching

채용공고의 요구사항을 다음 요소와 분리해 비교합니다.

- 기술
- 프로젝트 경험
- 주요 업무 경험
- 경력 / 학력 / 지역 / 고용 형태

결과는 단순 일치/불일치가 아니라 다음 상태로 구분합니다.

- 확인된 일치
- 부분 일치
- 확인된 부족 또는 불일치
- 현재 자료만으로 판단할 수 없는 항목

정보가 없다는 이유만으로 자동으로 역량 부족으로 처리하지 않는 것이 핵심 원칙입니다.

### Recommendation

분석 결과를 바탕으로 다음 정보를 생성합니다.

- 지원 시 강조할 강점
- 확인된 부족 역량
- 우선 확인이 필요한 질문
- 학습 과제
- 기존 포트폴리오 개선 과제
- 지원 판단과 그 근거

합격 가능성을 예측하지 않고, **현재 확인 가능한 데이터로 지원 여부를 판단하는 데 필요한 근거**를 제공합니다.

### Slack interface

- Slack Bolt 기반 Socket Mode 연결
- 허용 사용자 / 채널 검증
- 실제 Slack 호출 수신
- 분석 결과를 동일 스레드에 응답
- 첨부 문서의 비공개 저장
- 프로필 후보 추출 후 사용자 확인을 거치는 구조

## Design Decisions

### 1. 규칙 기반 비교를 먼저 구현

현재 핵심 매칭 엔진은 LLM의 자유로운 판단보다 구조화된 규칙을 우선합니다.

이유는 다음과 같습니다.

- 같은 입력에서 비슷한 판단을 재현하기 쉬움
- 어떤 근거 때문에 결과가 나왔는지 추적 가능
- "정보 부족"과 "역량 부족"을 명확하게 분리 가능
- 향후 LLM을 추가하더라도 검증 가능한 기준선을 유지할 수 있음

### 2. 사용자 원본 데이터와 공개 저장소 분리

이 저장소는 Public이기 때문에 실제 사용자 문서는 Git에 저장하지 않습니다.

실제 문서와 분석 결과는 `private-data/` 아래에서 관리하고, 저장소에는 비식별 예제 데이터와 스키마만 둡니다.

### 3. 한 번에 모든 채용사이트를 수집하지 않음

공식 RSS, 공개 API, 기업 ATS처럼 이용 조건이 명확한 소스부터 연결했습니다.

수집 범위를 크게 만드는 것보다 **출처가 명확하고 반복 실행 가능한 흐름**을 먼저 만드는 것을 우선했습니다.

## Tech Stack

- Python
- Slack Bolt
- Greenhouse Job Board API
- RSS / XML
- JSON
- unittest

## Repository Structure

```text
career-agent/
|-- docs/                 # PRD, schema, matching rules
|-- data/                 # public example data
|-- src/career_agent/
|   |-- discovery/        # job discovery and ranking
|   |-- ingestion/        # posting normalization
|   |-- matching/         # evidence-based matching
|   |-- interfaces/       # Slack event handling
|   |-- execution/        # run history
|   `-- workflows/        # end-to-end workflows
|-- scripts/              # local execution commands
|-- tests/                # matching and workflow tests
`-- private-data/         # local-only data, excluded from Git
```

## Run

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Run tests:

```bash
python -m unittest discover -s tests -v
```

Analyze one Greenhouse job:

```bash
python scripts/analyze_greenhouse_job.py --board <board-token> --job-id <job-id>
```

Run the limited Greenhouse agent workflow:

```bash
python scripts/run_greenhouse_agent.py
```

## Current Status

현재 확인한 흐름:

- 실제 Greenhouse 공고 조회 및 구조화
- 사용자 프로필과 요구사항 비교
- 분석 결과 JSON 저장
- 신규 공고 발견 및 중복 제거
- 검토 큐 생성
- 실제 Slack 호출과 스레드 응답
- 첨부 문서 비공개 저장과 프로필 후보 추출

아직 진행 중인 부분:

- Slack에서 프로필 후보 승인 후 실제 프로필 갱신까지의 대화 흐름
- 갱신된 프로필을 즉시 다음 공고 탐색에 연결
- 실제 관심 공고를 충분히 누적한 사용자 검증
- 채용 소스 확장
- LLM을 사용할 경우의 역할과 검증 경계 설계

## Documentation

상세 설계는 `docs/`에서 관리합니다.

- [PRD](docs/PRD.md)
- [Matching Rules](docs/MATCHING_RULES.md)
- [User Profile Schema](docs/USER_PROFILE_SCHEMA.md)
- [Job Posting Schema](docs/JOB_POSTING_SCHEMA.md)
- [Job Discovery Plan](docs/JOB_DISCOVERY_PLAN.md)
- [Slack Interface](docs/SLACK_INTERFACE.md)
