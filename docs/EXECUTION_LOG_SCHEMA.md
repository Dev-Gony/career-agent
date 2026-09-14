# Execution Log Schema

## 1. 목적

상세 분석을 새로 만들지 않은 실행도 실제로 어떤 보드를 확인했고 성공 또는 실패했는지 추적한다.

분석 결과 파일과 실행 이력 파일을 분리하여 다음을 구분한다.

- 외부 소스를 언제 확인했는가
- 보드별 목록 조회가 성공했는가
- 새 분석을 만들었는가
- 기존 분석을 재사용했는가
- 분석할 `high` 후보가 없었는가
- 실행이 실패했는가

## 2. 저장 위치

기본 저장 경로는 `private-data/execution-runs/`이다. 이 경로는 Git에서 제외한다.

각 실행은 마이크로초와 시간대를 포함한 고유 ID로 별도 JSON 파일에 저장하며 기존 파일을 덮어쓰지 않는다.

## 3. 상태

- `analyzed`: 새 상세 분석 생성
- `reused`: 기존 상세 분석 재사용
- `no_high_candidate`: 현재 `high` 후보가 없어 상세 분석하지 않음
- `failed`: 설정, 목록 조회, 분석 또는 저장 단계 실패

## 4. 최소 구조

    {
      "execution": {
        "execution_id": "greenhouse-run-20260914T102144311713+0900",
        "provider": "greenhouse",
        "status": "reused",
        "executed_at": "2026-09-14T10:21:44.311713+09:00"
      },
      "discovery": {
        "boards_requested": 1,
        "boards_succeeded": 1,
        "boards_failed": 0,
        "fetched_records": 10,
        "board_attempts": [
          {
            "board_token": "sendbird",
            "status": "succeeded",
            "fetched_records": 10
          }
        ]
      },
      "selection": {
        "board_token": "sendbird",
        "external_job_id": "8395379002"
      },
      "analysis_reference": {
        "analysis_id": "analysis-greenhouse-sendbird-8395379002-sample-user-001-...",
        "analysis_filename": "analysis-greenhouse-sendbird-8395379002-sample-user-001-....json",
        "reused": true
      },
      "error": null,
      "metadata": {
        "schema_version": "1.0",
        "contains_profile_content": false,
        "contains_job_description_content": false
      }
    }

## 5. 개인정보와 공고 데이터 경계

실행 이력에는 다음을 저장하지 않는다.

- 사용자 프로필 원문
- 경력, 프로젝트, 기술과 자기이해 자료
- 채용공고 본문
- 상세 매칭 판정 전체

분석이 있으면 분석 ID와 파일명만 참조한다. 보드 실행 결과도 현재 공고 목록 전체가 아니라 처리 건수와 성공·실패 정보만 저장한다.
