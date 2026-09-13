# Job Posting Schema

## 1. 목적

이 문서는 Career Agent가 채용공고를 일관된 방식으로 읽고 사용자 프로파일과 비교할 수 있도록 채용공고의 표준 구조를 정의한다.

구현 전 분석 검증에는 고정된 예제 공고를 사용한다. 이는 매칭 결과를 재현하기 위한 테스트 입력이며, 사용자의 반복적인 복사·붙여넣기를 최종 입력 방식으로 삼지 않는다. 자동 발견과 상세 수집의 경계는 `docs/JOB_DISCOVERY_PLAN.md`에서 별도로 정의한다.

## 2. 설계 원칙

채용공고 데이터는 다음 원칙을 따른다.

1. 원문에서 확인한 사실과 Agent가 해석한 내용을 구분한다.
2. 필수 조건과 우대 조건을 분리한다.
3. 기술 이름만 저장하지 않고 요구 수준과 맥락을 함께 기록한다.
4. 확인되지 않은 정보는 추정하지 않는다.
5. 채용공고의 출처와 수집 시점을 기록한다.
6. 나중에 같은 공고를 다시 분석할 수 있도록 식별 가능한 정보를 남긴다.

## 3. 최상위 구조

초기 채용공고 데이터는 다음 영역으로 나눈다.

    job_posting
    |-- identity
    |-- source
    |-- company
    |-- role
    |-- responsibilities
    |-- requirements
    |-- preferred_qualifications
    |-- technologies
    |-- experience
    |-- education
    |-- employment
    |-- location
    |-- compensation
    |-- work_environment
    |-- extracted_keywords
    |-- analysis_notes
    `-- raw_text

## 4. identity

공고를 구분하기 위한 최소 식별자다.

예시:

    identity:
      posting_id: "job-001"
      title: "AI Automation Engineer"
      status: "open"

권장 필드:

- `posting_id`: 내부 식별자
- `title`: 공고에 표시된 직무명
- `status`: open, closed, unknown

## 5. source

공고의 출처를 기록한다.

예시:

    source:
      platform: "wanted"
      url: "https://example.com/jobs/123"
      collected_at: "2026-09-13"
      input_method: "manual"

권장 필드:

- `platform`: 사람인, 잡코리아, 인크루트, 원티드, 기업 채용 페이지 등
- `url`: 공고 원문 URL
- `collected_at`: 수집 또는 확인 날짜
- `input_method`: manual, official_api, rss, search_api, ats_api, permitted_html 등

공개 예제와 고정 테스트 입력에는 `manual`을 사용할 수 있다. 실제 자동 처리에서는 발견 경로와 상세 내용의 출처를 구분할 수 있는 구체적인 값을 사용한다. `permitted_html`은 이용약관과 robots 정책을 모두 확인해 자동 접근이 허용된 경우에만 사용한다.

## 6. company

회사 관련 정보를 저장한다.

예시:

    company:
      name: "Example Company"
      industry: "software"
      size: "unknown"

공고에 없는 정보는 임의로 채우지 않는다.

## 7. role

직무 자체를 구조화한다.

예시:

    role:
      normalized_title: "AI Automation Engineer"
      category: "AI Automation"
      seniority: "junior_or_unknown"
      summary: "AI와 API를 활용해 반복 업무를 자동화하고 내부 운영 효율을 개선하는 역할"

`normalized_title`은 공고마다 표현이 다른 직무명을 비교하기 위해 사용하는 표준화 이름이다.

## 8. responsibilities

주요 업무를 원문 기준으로 구조화한다.

예시:

    responsibilities:
      - responsibility_id: "responsibility-001"
        text: "내부 반복 업무 자동화"
      - responsibility_id: "responsibility-002"
        text: "외부 API 연동"
      - responsibility_id: "responsibility-003"
        text: "LLM 기반 업무 도구 개발"
      - responsibility_id: "responsibility-004"
        text: "자동화 결과 모니터링 및 개선"

업무는 가능하면 한 항목에 한 의미만 담는다.

## 9. requirements

필수 조건을 저장한다.

예시:

    requirements:
      - requirement_id: "requirement-python"
        type: "skill"
        name: "Python"
        level: "required"
        evidence_text: "Python을 활용한 개발 경험"
      - requirement_id: "requirement-rest-api"
        type: "experience"
        name: "API integration"
        level: "required"
        evidence_text: "REST API 연동 경험"

권장 `type` 값:

- skill
- experience
- domain
- communication
- language
- certification
- other

`evidence_text`에는 원문에서 근거가 된 표현을 짧게 저장한다.

## 10. preferred_qualifications

우대 조건은 필수 조건과 별도로 저장한다.

예시:

    preferred_qualifications:
      - qualification_id: "qualification-docker"
        type: "skill"
        name: "Docker"
        evidence_text: "Docker 사용 경험 우대"
      - qualification_id: "qualification-aws"
        type: "cloud"
        name: "AWS"
        evidence_text: "AWS 환경 운영 경험 우대"

우대사항을 필수 조건처럼 취급하지 않는다.

## 11. technologies

공고에서 확인된 기술을 비교하기 쉬운 형태로 모은다.

예시:

    technologies:
      required:
        - "Python"
        - "REST API"
      preferred:
        - "Docker"
        - "AWS"
      mentioned:
        - "GitHub"
        - "Slack"

같은 기술이 여러 영역에 등장해도 중요도를 구분해 기록한다.

## 12. experience

경력 조건을 저장한다.

예시:

    experience:
      minimum_years: 0
      maximum_years: null
      level_text: "신입 또는 경력"
      equivalent_experience_allowed: true

공고가 모호하면 숫자를 임의로 추정하지 않고 `null`을 사용한다.

## 13. education

학력 조건을 저장한다.

예시:

    education:
      required: false
      level: "unknown"
      notes: null

학력 조건이 없는 경우에도 `unknown`과 `not_required`를 구분한다.

## 14. employment

고용 형태와 근무 방식을 저장한다.

예시:

    employment:
      type: "full_time"
      contract_period: null
      probation: "unknown"

권장 값:

- full_time
- contract
- internship
- freelance
- part_time
- unknown

## 15. location

근무 위치와 원격 여부를 저장한다.

예시:

    location:
      region: "서울"
      district: "강남구"
      remote: "hybrid"

상세 주소는 분석에 필요하지 않으면 저장하지 않는다.

## 16. compensation

연봉 또는 보상 정보가 공고에 있을 때만 저장한다.

예시:

    compensation:
      disclosed: false
      min: null
      max: null
      currency: "KRW"
      period: "annual"

정보가 없으면 추정하지 않는다.

## 17. work_environment

공고에서 업무 방식이나 조직 환경을 유추할 수 있는 명시적 정보를 저장한다.

예시:

    work_environment:
      collaboration:
        - "개발 및 운영팀과 협업"
      pace:
        - "빠른 실험과 개선"
      ownership:
        - "자동화 과제 발굴부터 운영까지 담당"

이 영역은 원문에 명시된 정보와 Agent의 해석을 섞지 않는다.

## 18. extracted_keywords

검색과 통계를 위한 키워드를 저장한다.

예시:

    extracted_keywords:
      role_keywords:
        - "automation"
        - "workflow"
        - "AI"
      skill_keywords:
        - "Python"
        - "API"
        - "Docker"
        - "AWS"

나중에 여러 공고에서 요구 기술 비율을 집계할 때 사용한다.

## 19. analysis_notes

Agent가 공고를 구조화하면서 남기는 해석 영역이다.

예시:

    analysis_notes:
      facts:
        - "Python은 필수 조건으로 명시됨"
        - "Docker는 우대 조건으로 명시됨"
      interpretations:
        - "단순 분석보다는 자동화 구현 비중이 높은 직무로 보임"
      unknowns:
        - "클라우드 사용 비중은 공고만으로 확인할 수 없음"

반드시 `facts`, `interpretations`, `unknowns`를 구분한다.

## 20. raw_text

초기 MVP에서는 사용자가 붙여넣은 공고 원문을 함께 저장할 수 있다.

예시:

    raw_text: "채용공고 원문..."

다만 공개 저장소의 예제 파일에는 실제 채용공고 전문을 저장하지 않는다.

실제 운영에서는 저작권, 이용약관, 저장 필요성을 고려해 원문 전체 보관 여부를 결정한다.

## 21. 항목 식별자

매칭 결과에서 배열 위치가 아니라 공고 항목을 안정적으로 참조할 수 있도록 주요 비교 항목에 ID를 둔다.

권장 필드:

- `responsibility_id`: 주요 업무
- `requirement_id`: 필수 조건
- `qualification_id`: 우대 조건

ID는 한 채용공고 안에서 중복되지 않아야 하며 항목 순서가 바뀌어도 변경하지 않는다. 같은 공고를 다시 수집해 문구가 조금 달라지더라도 같은 의미의 항목이면 가능한 한 기존 ID를 유지한다.

## 22. 비교에 필요한 최소 필드

Career Agent의 첫 매칭 테스트에 필요한 최소 항목은 다음과 같다.

- 직무명
- 주요 업무
- 필수 역량
- 우대 역량
- 기술 스택
- 경력 조건
- 근무 위치
- 출처 URL
- 공고 원문 또는 요약

이 최소 필드만으로도 사용자 프로파일과 첫 수동 비교 테스트를 진행할 수 있어야 한다.

## 23. 다음 단계

이 스키마를 기준으로 다음 작업을 진행한다.

1. `data/job_posting.example.json` 작성
2. `docs/MATCHING_RULES.md` 작성
3. 사용자 프로파일과 채용공고의 비교 항목 정의
4. 실제 채용공고 1개를 수동 입력
5. 첫 적합도 분석 결과 검토
