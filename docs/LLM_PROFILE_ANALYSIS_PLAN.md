# LLM Profile Analysis Plan

## 1. 목적

Slack 첨부자료에서 만든 비공개 문단 후보를 경력, 성과, 기술 사용 증거와 미확인 정보의 구조화 초안으로 변환한다.

LLM 결과는 사용자 사실의 최종 확정값이 아니다. 모든 항목은 원본 후보 ID와 문단 위치를 참조하고, 사용자 승인 전에는 개인 프로필과 검색 계획을 변경하지 않는다.

## 2. 외부 전송 승인 경계

- 사용자가 외부 LLM 전송과 과금 가능성을 명시적으로 확인하기 전에는 실제 이력서 후보를 API로 보내지 않는다.
- API Key는 로컬 `.env`에만 저장하고 Slack, Git, 작업일지와 실행 로그에 기록하지 않는다.
- 파일 자체를 업로드하지 않고 로컬에서 연락처 형태를 제외한 후보 문장만 한 요청에 포함한다.
- API 요청과 응답 원문은 일반 로그에 기록하지 않는다.
- 응답은 JSON Schema로 제한하고 로컬에서 다시 검증한다.
- 요청은 저장 기능과 외부 도구를 사용하지 않는 단일 텍스트 분석으로 제한한다.

## 3. 공급자 비교

| 선택지 | 데이터 사용 경계 | 구조화 출력 | 현재 판단 |
| --- | --- | --- | --- |
| Gemini API 무료 등급 | Google은 입력과 응답을 제품 개선에 사용할 수 있고 사람 검토 가능성을 명시하며 민감·기밀·개인정보를 보내지 말라고 안내함 | 지원 | 실제 이력서에 사용하지 않음 |
| Gemini API 유료 등급 | 입력과 응답을 제품 개선에 사용하지 않지만 안전 목적의 제한적 로그가 있을 수 있음 | 지원 | 유료 Cloud Billing을 사용자가 확인한 경우 대안 |
| OpenAI API 일반 계정 | 기본적으로 입력과 출력을 모델 학습에 사용하지 않음. 악용 방지 로그에 고객 콘텐츠가 포함될 수 있고 기본 최대 30일 보관 | 지원 | 개인용 MVP 권고안 |
| 완전 로컬 모델 | 외부 전송 없음 | 모델과 실행 환경에 따라 다름 | 현재 사용자의 운영 경험과 PC 자원 확인 전에는 우선하지 않음 |

공식 근거:

- OpenAI API 데이터 제어: https://developers.openai.com/api/docs/guides/your-data
- OpenAI API 모델 목록: https://developers.openai.com/api/docs/models
- OpenAI GPT-5.6 Luna: https://developers.openai.com/api/docs/models/gpt-5.6-luna
- Gemini API 추가 약관: https://ai.google.dev/gemini-api/terms
- Gemini API 가격 및 무료 등급: https://ai.google.dev/gemini-api/docs/pricing
- Gemini Generate Content API: https://ai.google.dev/api/generate-content
- Gemini 구조화 출력: https://ai.google.dev/gemini-api/docs/structured-output
- Gemini 모델 목록: https://ai.google.dev/gemini-api/docs/models
- Gemini API 오류 해결: https://ai.google.dev/gemini-api/docs/troubleshooting

## 4. 현재 개발용 구성

- 공급자: Gemini API 무료 등급
- 입력: 기본은 공개 합성 문서, 실제 문서는 문서별 최신 Slack 승인이 정확히 일치할 때만 허용
- 개발 모델: `gemini-3.5-flash-lite`
- API: `generateContent`
- 응답 형식: JSON Schema
- reasoning effort: `low`
- 외부 검색, 파일 검색, 코드 실행과 다른 도구: 사용하지 않음

공개 합성 어댑터는 기존 fixture 지문 제한을 그대로 유지한다. 실제 문서용 어댑터는 별도로 두며, 문서 추출 ID와 최소 요청 지문, 공급자·모델, 최신 Slack 세션과 승인 기록이 모두 일치한 뒤에만 실행한다. 파일명, 문서 ID, 로컬 경로와 연락처 형태는 공급자 요청에 넣지 않는다.

OpenAI 어댑터는 공급자 중립 경계를 검증한 구현으로 보존하지만 현재 개발 테스트에는 사용하지 않는다. 실제 서비스 공급자, 장기 컨텍스트, 프롬프트 하네스와 개인정보 처리 조건은 배포 전 별도 결정한다.

## 5. 첫 JSON 출력 계약

첫 구현은 다음 항목만 생성한다.

- `career_evidence`: 역할, 기간 표현, 책임과 행동의 초안
- `achievement_evidence`: 문제, 행동, 수치 결과 표현의 초안
- `technology_evidence`: 기술명, 사용 맥락과 숙련도 미확인 상태
- `unknowns`: 원문만으로 확정할 수 없는 항목
- 모든 항목의 `candidate_ids`: 원본 후보 참조
- 모든 항목의 `confidence`: `high`, `medium`, `low`

모델이 회사명, 기간, 기술, 성과 수치 또는 숙련도를 원문에 없는 내용으로 보완하면 로컬 검증에서 거부한다. 연락처, 상세 주소와 식별정보는 입력과 출력 계약에서 제외한다.

## 6. 완료 기준

1. 합성 이력서 후보로 JSON Schema 검증과 근거 참조 검증이 통과한다.
2. API Key가 없어도 전체 기존 테스트와 Slack 공고 분석은 정상 동작한다.
3. 실제 사용자 문서는 Gemini 무료 등급의 데이터 사용 가능성을 안내받고 해당 문서를 명시적으로 승인한 경우에만 호출한다.
4. 실제 이력서 결과를 Slack에 표시해 사용자가 승인하거나 거부할 수 있다.
5. 승인 전 기존 사용자 프로필은 변경되지 않는다.

## 7. 아직 결정하지 않은 점

- 실제 서비스에서 사용할 LLM 공급자와 모델
- 실제 개인 문서를 외부 공급자에 보낼 때 적용할 데이터 처리 조건과 동의 방식
- 장기 컨텍스트, 프롬프트 하네스와 평가 데이터 구성

## 8. 구현 현황

2026-09-21 기준으로 공급자 응답용 strict JSON Schema와 로컬 검증기를 합성 데이터로 구현했다. 존재하지 않는 후보 ID, 참조 후보 원문에 없는 사실 표현, 확정된 기술 숙련도와 허용되지 않은 필드는 거부한다. 검증된 결과는 사용자 검토 전 비공개 분석 초안으로만 저장하며 기존 프로필을 변경하지 않는다. 공급자 중립 인터페이스와 로컬 합성 공급자 흐름을 추가했고, 외부 공급자는 명시적 전송 승인 없이는 호출 전에 차단한다.

OpenAI Responses API 어댑터와 로컬 실행 명령을 추가했다. 요청은 `https://api.openai.com/v1/responses` 한 곳만 사용하고 리디렉션을 따르지 않으며, `store: false`, strict JSON Schema, 도구 없음과 낮은 추론 수준을 고정한다. 후보 ID·프로필 섹션·후보 문장 외 필드가 공급자 요청에 들어가면 네트워크 호출 전에 거부한다. API 오류 본문, API Key와 후보 문장은 콘솔 오류에 출력하지 않는다.

Gemini 공개 합성 어댑터와 명시적 승인 기반 실제 문서 어댑터를 분리했다. 두 경로 모두 `gemini-3.5-flash-lite`, `thinkingLevel: low`, JSON Schema와 도구 없는 단일 요청을 사용한다. 실제 문서 경로는 최신 승인 기록 검증 후에만 최소 후보를 보내며, Gemini 요청에서 지원되지 않은 문자열·배열 제약은 제거하더라도 동일한 제한과 원문 근거 검증은 로컬에서 다시 수행한다.

공개 합성 문서와 사용자가 명시적으로 승인한 실제 이력서 후보의 Gemini 호출을 확인했다. 첫 실제 응답의 요약 근거는 로컬 원문 검증에서 차단됐고, 원문 구간 복사 계약을 강화한 재호출은 경력 2개, 성과 3개, 기술 11개의 비공개 검토 초안으로 저장됐다. 개인 프로필 변경은 발생하지 않았다. Slack 승인 응답에서도 같은 검증 경계를 거쳐 실제 분석을 실행하도록 연결했다.
