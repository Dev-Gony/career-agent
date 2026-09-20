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
- Gemini 구조화 출력: https://ai.google.dev/gemini-api/docs/structured-output

## 4. MVP 권고 구성

- 공급자: OpenAI API
- 개발 모델: `gpt-5.6-luna`
- 품질 비교 모델: `gpt-5.6-terra`
- API: Responses API
- 응답 형식: strict JSON Schema
- 저장 옵션: `store: false`
- reasoning effort: `low`
- 외부 검색, 파일 검색, 코드 실행과 다른 도구: 사용하지 않음

`gpt-5.6-luna`는 공식 문서에서 비용 민감형 모델로 안내되고 Structured Outputs를 지원한다. 이력서 한 건의 구조화 품질이 부족하면 전체 시스템을 바꾸지 않고 같은 계약으로 `gpt-5.6-terra` 결과와 비교한다.

`store: false`는 Responses API의 애플리케이션 상태 저장을 줄이기 위한 설정이다. 일반 계정의 최대 30일 악용 방지 로그까지 제거하는 Zero Data Retention을 의미하지 않는다.

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
3. 사용자가 외부 전송과 과금을 확인한 뒤에만 실제 API 호출을 활성화한다.
4. 실제 이력서 결과를 Slack에 표시해 사용자가 승인하거나 거부할 수 있다.
5. 승인 전 기존 사용자 프로필은 변경되지 않는다.

## 7. 아직 결정하지 않은 점

- 사용자의 OpenAI API 결제 및 API Key 준비 여부
- 일반 API의 최대 30일 악용 방지 로그를 개인 이력서 처리에 허용할지 여부
- Luna와 Terra 중 실제 한국어 이력서에서 필요한 최소 모델

## 8. 구현 현황

2026-09-20 기준으로 공급자 응답용 strict JSON Schema와 로컬 검증기를 합성 데이터로 구현했다. 존재하지 않는 후보 ID, 참조 후보 원문에 없는 사실 표현, 확정된 기술 숙련도와 허용되지 않은 필드는 거부한다. 검증된 결과는 사용자 검토 전 비공개 분석 초안으로만 저장하며 기존 프로필을 변경하지 않는다.

아직 공급자 호출 인터페이스, OpenAI API 구현, 실제 이력서 전송과 Slack 승인 대화는 연결하지 않았다.
