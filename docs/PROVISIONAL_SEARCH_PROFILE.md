# Provisional Search Profile

## 목적

사용자 확인 전인 프로필 분석 초안을 영구 프로필로 확정하지 않고 개인용 MVP의 공고 검색에 제한적으로 사용한다. 이 결과는 검색용 임시 투영이며 프로필 활성화 기록을 만들거나 기존 프로필을 변경하지 않는다.

## 입력과 출력

- 입력: 목표 직무와 선호 조건이 있는 기준 프로필, 검증된 `needs_review` 분석 초안
- 출력: Git 추적이 금지된 `provisional_search_only` 프로필
- 저장 권장 위치: `private-data/provisional-search-profiles/`

출력은 기준 프로필의 목표 직무, 선호 조건과 확정 근거를 보존한다. 분석 초안의 경력과 성과는 `profile.provisional_evidence`에 `unconfirmed` 상태로 보관하고 확정 `career_history`에는 넣지 않는다.

초안에서 찾은 새 기술은 다음 경계로 추가한다.

- `level`: `unconfirmed`
- `verification_status`: `unconfirmed`
- `provenance`: 원본 초안 ID, 후보 ID, 분석 신뢰도
- 검색 계획 중요도: `supporting`

기준 프로필에 같은 기술이 이미 있으면 확정 기술 항목을 수정하거나 낮추지 않는다. 초안 근거는 `provisional_evidence`에 별도로 남긴다.

## 검색 계획 경계

임시 기술은 검색어와 순위를 보조할 수 있지만 확인된 실무 또는 프로젝트 기술로 취급하지 않는다. 검색 계획에는 `provisional_profile_evidence` 미확정 제약을 남긴다. 프로필 최종 승인과 활성화는 기존 별도 흐름을 사용한다.

## 무결성과 개인정보

투영 ID는 기준 프로필 지문, 초안 ID, 출력 프로필 지문과 규칙 버전으로 결정한다. 저장과 로드 시 정확한 기준 프로필과 초안을 다시 대조하며 변조된 출력은 거부한다. 후보 문장을 포함할 수 있으므로 공개 저장소에 커밋하지 않는다.
