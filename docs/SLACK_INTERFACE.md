# Slack Interface

## 1. 목적

Slack 채널에서 사용자가 Career Agent를 호출하는 첫 입력 경계를 정의한다. 이번 버전은 실제 Slack 연결이나 공고 분석 실행이 아니라, 합성 `app_mention` 이벤트를 검증하고 허용된 내부 동작 요청으로 변환하는 로컬 단계다.

    Slack app_mention 예제
    -> 워크스페이스·앱·사용자·채널 검증
    -> 명령 식별
    -> 실행하지 않은 내부 요청 저장

## 2. 공식 이벤트 계약

Slack Events API는 바깥 이벤트의 `type`이 `event_callback`이고 실제 이벤트를 `event` 객체에 담아 전달한다. 채널에서 봇을 직접 호출하는 최소 구독 이벤트는 `app_mention`이며 `app_mentions:read` 권한이 필요하다.

- Events API: https://docs.slack.dev/apis/events-api/
- `app_mention`: https://docs.slack.dev/reference/events/app_mention

Slack은 이벤트 수신 확인이 늦거나 실패하면 같은 이벤트를 재전송할 수 있다. 따라서 `team_id`와 `event_id`로 요청 ID를 결정하고 같은 이벤트는 기존 요청을 재사용한다.

## 3. 로컬 설정

공개 합성 설정은 `data/slack_interface.example.json`이다.

    slack_interface:
      team_id: "T01234567"
      api_app_id: "A01234567"
      bot_user_id: "U01234567"
      allowed_user_ids:
        - "U76543210"
      allowed_channel_ids:
        - "C01234567"

    metadata:
      schema_version: "0.1"
      contains_secrets: false

실제 설정은 `private-data/` 아래에 두고 Git에 커밋하지 않는다. Bot Token, App Token, Signing Secret은 이 JSON에 넣지 않고 이후 환경 변수로만 받는다.

허용 사용자와 채널 목록은 비어 있을 수 없다. 일치하지 않는 사용자나 채널의 이벤트는 내부 동작으로 연결하지 않는다.

## 4. 지원 명령

현재 지원하는 사용자 문장은 하나다.

    <@봇사용자ID> 다음 공고 찾아줘

공백과 봇 호출 위치만 정규화한다. 비슷한 다른 문장을 Agent가 같은 뜻이라고 임의로 추정하지 않는다.

    command_name: "find_next_job"
    action: "analyze_next_greenhouse_review"

이 동작은 기존 `scripts/analyze_next_greenhouse_review.py`의 “검토 큐에서 다음 공고 1건 분석” 기능을 가리킨다. 현재 변환기는 동작 이름만 식별하며 실제 네트워크 요청이나 공고 분석은 실행하지 않는다.

## 5. 내부 요청 구조

    slack_command_request:
      request_id: "slack-command-request-example"
      routing_status: "action_identified"
      command_name: "find_next_job"
      action: "analyze_next_greenhouse_review"
      execution_status: "not_executed"
      reason: "supported_command"

    source:
      event_id: "Ev01234567"
      team_id: "T01234567"
      api_app_id: "A01234567"
      user_id: "U76543210"
      channel_id: "C01234567"

    metadata:
      schema_version: "0.1"
      contains_message_text: false
      git_tracking_allowed: false
      network_request_verified: false
      local_validation_only: true

사용자가 쓴 메시지 원문은 저장하지 않는다. 결과는 `private-data/slack-command-requests/`에 저장한다.

## 6. 로컬 확인

    python scripts/parse_slack_event.py

기본 합성 이벤트와 설정을 사용하면 `find_next_job`, `analyze_next_greenhouse_review`, `not_executed`가 출력된다. 같은 명령을 다시 실행하면 동일한 Slack 이벤트 요청을 재사용한다.

이 명령은 Slack에 접속하지 않고 실제 공고도 분석하지 않는다.

## 7. 실제 Slack 연결 선택

개인용 로컬 MVP의 첫 연결 방식은 Socket Mode가 적합하다. Socket Mode는 공개 HTTP Request URL 대신 WebSocket 연결을 사용하므로 AWS, Docker 또는 외부 공개 서버 없이 로컬 PC에서 시험할 수 있다.

- Socket Mode: https://docs.slack.dev/apis/events-api/using-socket-mode/

실제 연결 단계에서는 다음 정보가 필요하다.

- Slack 워크스페이스에서 생성한 앱
- 앱의 `team_id`, `api_app_id`, `bot_user_id`
- 허용할 본인 Slack 사용자 ID와 테스트 채널 ID
- `app_mentions:read` Bot Token Scope
- Socket Mode용 App Token
- 응답 전송을 위한 Bot Token

Token은 저장소 파일이나 작업일지에 기록하지 않는다.

## 8. 현재 보안 경계와 다음 단계

HTTP Request URL 방식은 Slack Signing Secret으로 요청 서명을 반드시 확인해야 한다.

- Slack 요청 서명 검증: https://docs.slack.dev/authentication/verifying-requests-from-slack

현재 로컬 변환 결과의 `network_request_verified`는 항상 `false`이며 `execution_status`도 `not_executed`다. 따라서 실제 Slack 요청을 이 함수에 직접 넣어 실행하면 안 된다.

다음 단계에서는 Socket Mode 연결을 별도 어댑터로 만들고 다음 순서로 처리한다.

1. 환경 변수에서 App Token과 Bot Token을 읽는다.
2. Slack 연결이 인증한 이벤트만 현재 변환기에 전달한다.
3. 요청을 먼저 확인 응답한 뒤 내부 작업을 분리 실행한다.
4. 완료 또는 실패 결과를 원래 채널에 보낸다.
5. 동일 `event_id` 재전송은 다시 분석하지 않는다.
