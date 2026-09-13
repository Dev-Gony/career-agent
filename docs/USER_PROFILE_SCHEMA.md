# User Profile Schema

## 1. 목적

이 문서는 Career Agent가 사용자의 자기이해 자료, 경력, 프로젝트, 기술 역량, 관심 직무를 일관된 방식으로 읽고 비교할 수 있도록 사용자 프로파일의 표준 구조를 정의한다.

초기 버전은 개인용으로 사용한다. 공개 저장소에는 원본 검사 결과나 민감한 개인정보를 그대로 저장하지 않고, 분석에 필요한 수준으로 요약한 비식별 정보만 기록한다.

## 2. 설계 원칙

사용자 프로파일의 판단 우선순위는 다음과 같다.

1. 실제 경력과 행동 사례
2. 프로젝트와 산출물
3. 기술 역량과 사용 증거
4. 적성 및 직무 관련 검사
5. 성격 및 강점 검사
6. 자기평가와 관심 직무

성격검사 하나의 결과로 직무 적합도를 단정하지 않는다.

프로파일의 모든 주요 판단에는 가능한 경우 근거를 함께 저장한다.

예:

- "Python 가능"이 아니라 "GitHub Actions 기반 자동화 프로젝트에서 Python 사용"
- "문제해결력이 높음"이 아니라 "서버비 이상을 발견하고 사용량과 사양을 비교해 비용 절감"

## 3. 최상위 구조

초기 사용자 프로파일은 다음 영역으로 나눈다.

    profile
    |-- basic
    |-- career_goals
    |-- career_history
    |-- education
    |-- projects
    |-- skills
    |-- behavior_evidence
    |-- assessments
    |-- work_preferences
    |-- learning_preferences
    |-- strengths
    |-- risks
    |-- target_roles
    `-- evidence_sources

## 4. basic

분석에 꼭 필요한 최소 정보만 저장한다.

필드 예시:

    basic:
      profile_id: "user-001"
      locale: "ko-KR"
      career_status: "job_seeker"
      location_preference:
        - "수도권"
      employment_type_preference:
        - "정규직"

저장하지 않는 정보:

- 주민등록번호
- 상세 주소
- 개인 전화번호
- 개인 이메일
- 계정 비밀번호
- 기타 취업 분석에 필요하지 않은 개인정보

## 5. career_goals

현재 취업 목표를 저장한다.

필드 예시:

    career_goals:
      primary_goal: "AI 및 자동화 관련 직무 취업"
      priorities:
        - "실제 문제를 해결하는 업무"
        - "자동화 및 AI 활용"
        - "눈에 보이는 결과가 있는 업무"
      avoid_if_possible:
        - "반복적인 수작업 중심 업무"
        - "분석 결과를 정기 리포트로만 끝내는 업무"

이 영역은 고정된 성격 특성이 아니라 현재의 취업 전략이므로 수정 가능해야 한다.

## 6. career_history

실제 직장 경험을 구조화한다.

각 경력 항목은 다음 구조를 권장한다.

    career_history:
      - career_id: "career-001"
        organization_type: "비공개 또는 업종 수준"
        role: "웹개발 및 유지보수"
        period: "YYYY-MM ~ YYYY-MM"
        duration_years: 3.5
        responsibilities:
          - "웹 개발 및 유지보수"
          - "서버 운영 관련 업무"
        achievements:
          - achievement_id: "achievement-001"
            title: "서버 비용 최적화"
            problem: "기존 서버 사양과 비용이 실제 사용량 대비 과도하다고 판단"
            actions:
              - "과거 사용량과 현재 서버 사양 비교"
              - "축소 가능 사양 검토"
              - "리스크와 재증설 가능성을 포함해 제안"
              - "승인 후 서버 사양 조정"
              - "정상 운영 여부 확인"
            result: "서버 관련 비용을 크게 절감"
            evidence_level: "real_work"

정확한 수치가 확인되지 않은 경우 추정치를 사실처럼 저장하지 않는다. `duration_years`는 해당 경력의 확인된 연수를 0 이상의 숫자로 기록하며, 비공개이거나 계산할 수 없으면 `null`을 사용한다.

## 6.1 education

공고의 필수 학력 조건과 비교하는 데 필요한 최소 정보만 저장한다.

    education:
      level: "unknown"
      field: null
      status: "unknown"
      notes: "이력서에서 아직 확인하지 않음"

권장 `level` 값:

- high_school
- associate
- bachelor
- master
- doctorate
- unknown

`status`는 `completed`, `in_progress`, `unknown`을 사용한다. 학력 정보가 없거나 공개 예제에서 비식별화한 경우 `unknown`으로 유지하며, 임의로 최종 학력을 추정하지 않는다.

## 7. projects

개인 프로젝트와 팀 프로젝트를 구조화한다.

권장 필드:

    projects:
      - project_id: "project-tech-news"
        name: "Tech News Automation"
        type: "personal"
        status: "completed"
        problem: "여러 기술 블로그의 새 글을 반복적으로 확인해야 하는 문제"
        solution: "기술 블로그 글을 수집하고 LLM으로 요약하여 Slack에 정기 전달"
        technologies:
          - "Python"
          - "Gemini API"
          - "GitHub Actions"
          - "Slack Webhook"
        capabilities_demonstrated:
          - "외부 데이터 수집"
          - "중복 방지"
          - "LLM 요약"
          - "상태 관리"
          - "재시도 처리"
          - "예약 자동 실행"
        evidence:
          repository: "Dev-Gony/technews"
          demo_available: true

프로젝트는 단순 기술 목록보다 문제, 해결 방식, 실제 결과, 증명 가능한 산출물을 중심으로 저장한다.

## 8. skills

기술 역량은 보유 여부가 아니라 수준과 증거를 함께 저장한다.

권장 수준:

- none: 직접 사용 경험이 없음을 확인함
- exposure: 설치, 화면 확인 또는 개념 접촉만 했으며 과제를 완료한 경험은 없음
- learning: 학습 중
- basic: 기본 사용 가능
- project: 프로젝트 사용 경험
- work: 실무 사용 경험

예:

    skills:
      - skill_id: "skill-python"
        name: "Python"
        level: "project"
        evidence:
          - "Tech News Automation"
        notes: "자동화 스크립트 및 API 연동 경험"

      - skill_id: "skill-sql"
        name: "SQL"
        level: "learning"
        evidence:
          - "STA 교육 과정"

      - skill_id: "skill-github-actions"
        name: "GitHub Actions"
        level: "project"
        evidence:
          - "Tech News Automation 정기 실행"

기술 수준은 Agent가 임의로 과장하지 않는다.

`none`과 `exposure`는 보유 기술을 강조하기 위한 값이 아니라 확인된 부족과 정보 부족을 구분하기 위한 값이다. 설치만 했거나 도구 화면만 확인한 경험을 `basic` 또는 `learning`으로 올리지 않는다.

## 9. behavior_evidence

실제 행동에서 반복적으로 확인된 문제해결 패턴을 저장한다.

예:

    behavior_evidence:
      - behavior_id: "behavior-server-cost"
        situation: "서버 비용 이상"
        pattern:
          - "비효율 감지"
          - "사용량과 사양 비교"
          - "리스크 검토"
          - "개선 실행"
          - "정상 운영 확인"
        interpretation: "비효율 탐지와 구조적 개선"

      - behavior_id: "behavior-repetitive-check"
        situation: "반복 확인 업무"
        pattern:
          - "반복 문제 인식"
          - "데이터와 규칙 정리"
          - "자동화 구현"
          - "정기 실행"
        interpretation: "반복 업무를 자동화로 제거"

이 영역은 성격검사보다 높은 우선순위의 근거로 사용한다.

## 10. assessments

검사 결과는 원점수 전체를 그대로 저장하기보다 직무 분석에 필요한 핵심 요약을 저장한다.

예:

    assessments:
      big_five:
        summary:
          - "개방성이 높음"
          - "질서감과 자기훈련은 상대적으로 낮음"
        role_in_analysis: "supporting"

      via:
        summary:
          - "호기심과 창의성이 상위 강점"
        role_in_analysis: "supporting"

      hexaco:
        summary:
          - "개방성 관련 특성이 상대적으로 높음"
        role_in_analysis: "supporting"

      situational_judgment:
        summary:
          - "근거 확인 후 판단하는 경향"
          - "자유시간에서 실행 구조가 약해질 수 있음"
        role_in_analysis: "supporting"

모든 검사는 직무를 확정하는 판정기가 아니라 보조 근거로 취급한다.

## 11. work_preferences

현재까지 관찰된 업무 선호를 저장한다.

예:

    work_preferences:
      preferred:
        - "문제가 명확한 업무"
        - "해결 방법에 자율성이 있는 환경"
        - "결과를 직접 확인할 수 있는 업무"
        - "비효율을 개선하거나 자동화하는 업무"
        - "짧고 근거 중심의 협업"
      less_preferred:
        - "목적이 불명확한 반복 업무"
        - "장시간 회의 중심 환경"
        - "분석-only 정기 보고 중심 업무"

## 12. learning_preferences

학습 방식은 취업 역량 보완 추천에 사용한다.

예:

    learning_preferences:
      approach: "project_first"
      preferred_flow:
        - "문제 정의"
        - "작은 산출물 정의"
        - "구현"
        - "막힌 개념 학습"
        - "작동 확인"
        - "핵심 구조 설명"
        - "최소 기록"
      avoid:
        - "기술명만 정한 추상적인 공부 목표"
        - "완강 자체를 목표로 하는 장기 학습"

## 13. strengths

현재 프로파일에서 반복적으로 나타난 강점 후보를 저장한다.

예:

    strengths:
      - "비효율과 이상을 발견하는 탐지력"
      - "검색, AI, 문서, 로그를 조합한 원인 탐색"
      - "새로운 방법을 작은 위험 범위에서 실험"
      - "문제 해결 결과를 실제 변화로 연결"
      - "근거를 바탕으로 의견을 수정하는 판단 방식"

## 14. risks

취업 및 학습 전략에 영향을 줄 수 있는 실행 리스크를 저장한다.

예:

    risks:
      - risk: "새 아이디어로 프로젝트 전환"
        mitigation: "핵심 프로젝트 완료 전 새 아이디어는 backlog에 저장"
      - risk: "문서화 생략"
        mitigation: "완료 조건에 README 업데이트 포함"
      - risk: "자유시간에서 시작 지연"
        mitigation: "첫 행동을 15분 안에 완료 가능한 결과로 정의"

이 정보는 사용자를 부정적으로 평가하기 위한 것이 아니라 실행 전략을 설계하기 위해 사용한다.

## 15. target_roles

현재 탐색할 직무 가설을 저장한다.

초기 예시:

    target_roles:
      - target_role_id: "role-ai-automation"
        role: "AI Automation / Workflow Engineer"
        priority: 1
        hypothesis: "실제 문제를 데이터, API, AI, 자동화로 연결하는 패턴과 높은 일치"

      - target_role_id: "role-ai-solutions"
        role: "AI Solutions Engineer"
        priority: 2
        hypothesis: "문제 정의, PoC, 구축, 효과 확인 과정과 연관"

      - target_role_id: "role-enterprise-solution"
        role: "Enterprise Solution / ITSM"
        priority: 3
        hypothesis: "프로세스와 워크플로 개선 경험과 연결"

      - target_role_id: "role-cloud-finops"
        role: "Cloud / FinOps Automation"
        priority: 4
        hypothesis: "서버 비용 최적화 경험과 연결 가능"

      - target_role_id: "role-data-analytics-automation"
        role: "Data Analyst / Analytics Automation"
        priority: "conditional"
        hypothesis: "분석 결과를 자동화나 행동으로 연결할 경우 적합도 상승 가능"

이 목록은 고정하지 않는다. 실제 채용공고 분석 결과와 사용자의 흥미 변화에 따라 수정한다.

## 16. evidence_sources

프로파일의 각 판단이 어디에서 나왔는지 추적하기 위한 영역이다.

예:

    evidence_sources:
      - id: "profile-report-v3"
        type: "self_analysis_report"
        title: "통합 자기이해·학습·직무 프로파일 v3"
        date: "2026-09-13"
        storage: "private"

      - id: "technews-repo"
        type: "github_project"
        title: "Tech News Automation"
        storage: "public"

원본 개인정보 문서는 공개 저장소에 올리지 않는다.

## 17. 항목 식별자

결과 데이터에서 배열 위치가 아니라 항목을 안정적으로 참조할 수 있도록 주요 항목에 ID를 둔다.

권장 필드:

- `career_id`: 경력 항목
- `achievement_id`: 경력 성과
- `project_id`: 프로젝트
- `skill_id`: 기술
- `behavior_id`: 행동 사례
- `target_role_id`: 목표 직무
- `evidence_sources[].id`: 외부 또는 원본 근거

ID는 프로파일 안에서 중복되지 않아야 하며 항목 순서가 바뀌어도 변경하지 않는다. 이름이 수정되더라도 같은 대상을 의미하면 기존 ID를 유지한다.

## 18. 분석 시 우선순위 규칙

Career Agent는 직무 또는 채용공고와 사용자를 비교할 때 다음 순서로 근거를 사용한다.

1. 해당 요구사항을 증명하는 실무 경험이 있는가
2. 관련 프로젝트에서 실제로 사용했는가
3. 유사한 문제를 해결한 행동 사례가 있는가
4. 관련 기술을 학습하거나 기본 수준으로 사용할 수 있는가
5. 업무 성향과 직무 환경이 맞는가
6. 검사 결과가 이를 보조하는가

검사 결과가 실제 행동 근거와 충돌할 경우 실제 행동 근거를 우선한다.

## 19. 적합도 분석을 위한 기본 분류

각 채용 요구사항은 사용자 프로파일과 비교하여 다음 중 하나로 분류한다.

- strong_match: 직접적인 실무 또는 프로젝트 증거가 있음
- match: 관련 경험이나 유사 증거가 있음
- partial: 일부 경험이 있으나 요구 수준에는 부족함
- gap: 현재 증거가 없음
- unknown: 정보 부족으로 판단 불가

`unknown`을 자동으로 `gap`으로 처리하지 않는다.

## 20. 공개 저장소와 개인 데이터 분리

이 프로젝트는 Public 저장소이므로 실제 사용자 프로파일 원본은 저장소에 직접 커밋하지 않는다.

권장 구조:

    career-agent/
    |-- docs/
    |   |-- PRD.md
    |   `-- USER_PROFILE_SCHEMA.md
    |-- data/
    |   `-- user_profile.example.json
    `-- private-data/        로컬 전용, Git 제외

향후 구현 시 `private-data/`는 `.gitignore`에 포함한다.

공개 저장소에는 가상의 예제 데이터 또는 비식별 샘플만 저장한다.

## 21. 다음 단계

1. 이 스키마를 기준으로 `user_profile.example.json`을 만든다.
2. 실제 개인 프로파일은 로컬 전용 파일로 작성한다.
3. 채용공고 입력 스키마를 별도로 정의한다.
4. 사용자 프로파일과 채용공고를 비교하는 첫 분석 규칙을 만든다.
5. 실제 채용공고 1개로 수동 테스트한다.
