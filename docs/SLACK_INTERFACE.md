# Slack Interface

## 1. 목적

Slack 채널에서 사용자가 Career Agent를 호출하는 첫 입력 경계를 정의한다. 현재 실제 Slack 앱의 Token 인증과 개인 허용 목록 설정까지 완료했으며, 합성 `app_mention` 이벤트를 검증하고 허용된 내부 동작 요청으로 변환할 수 있다. 실제 Socket Mode 이벤트 수신과 공고 분석 실행은 아직 연결하지 않았다.

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

## 7. Slack 앱 생성과 권한 확인

개인용 로컬 MVP의 첫 연결 방식은 Socket Mode가 적합하다. Socket Mode는 공개 HTTP Request URL 대신 WebSocket 연결을 사용하므로 AWS, Docker 또는 외부 공개 서버 없이 로컬 PC에서 시험할 수 있다.

- Socket Mode: https://docs.slack.dev/apis/events-api/using-socket-mode/
- Bolt for Python 시작 안내: https://docs.slack.dev/tools/bolt-python/getting-started

저장소의 `data/slack_app_manifest.example.json`은 다음 최소 권한만 요청한다.

- `app_mentions:read`: 봇을 호출한 채널 메시지 수신
- `chat:write`: 처리 결과를 채널에 답변
- `app_mention`: 구독 이벤트
- `connections:write`: manifest의 Bot Token Scope가 아니라 별도로 만드는 Socket Mode App Token의 권한

사용자가 Slack에서 확인할 순서는 다음과 같다.

1. https://api.slack.com/apps 에 로그인한다.
2. 새 앱 만들기에서 manifest를 사용하는 방식을 선택한다.
3. 사용할 워크스페이스를 선택한다.
4. `data/slack_app_manifest.example.json` 전체 내용을 붙여넣는다.
5. 표시되는 앱 기능과 권한을 확인한 뒤 앱을 생성한다.
6. `OAuth & Permissions`에서 워크스페이스 설치를 시도한다.
7. 설치와 허용 화면이 완료되면 앱 설치 권한이 있는 것이다.
8. 관리자 승인이나 제한 메시지가 나오면 해당 워크스페이스에는 직접 설치 권한이 없는 것이다.

회사 워크스페이스에서 설치가 제한되면 개인 테스트용 Slack 워크스페이스를 만들어 그곳에서 먼저 검증할 수 있다. 이 프로젝트는 개인용 MVP이므로 초기 검증에 회사 워크스페이스가 필요하지 않다.

앱 설치 뒤에는 `Basic Information`의 App-Level Tokens에서 `connections:write`만 가진 App Token을 만들고, `OAuth & Permissions`에서 Bot Token을 확인한다.

실제 연결 단계에서는 다음 정보가 필요하다.

- Slack 워크스페이스에서 생성한 앱
- 앱의 `team_id`, `api_app_id`, `bot_user_id`
- 허용할 본인 Slack 사용자 ID와 테스트 채널 ID
- `app_mentions:read` Bot Token Scope
- Socket Mode용 App Token
- 응답 전송을 위한 Bot Token

Token은 저장소 파일이나 작업일지에 기록하지 않는다.

## 8. 로컬 비밀정보와 준비 검사

먼저 환경 변수 예제를 실제 비공개 파일로 복사한다.

    Copy-Item .env.example .env

`.env`에는 Slack 화면에서 복사한 값을 본인 PC에서만 입력한다.

    SLACK_APP_TOKEN=xapp-실제값
    SLACK_BOT_TOKEN=xoxb-실제값

Token 인증을 마치면 출력된 인증 결과 ID와 Slack 화면에서 확인한 App ID, 본인 User ID, 테스트 Channel ID로 비공개 허용 설정을 만든다.

    python scripts/configure_slack_interface.py `
      --auth-id slack-auth-인증결과ID `
      --app-id A앱ID `
      --user-id U사용자ID `
      --channel-id C채널ID

이 명령은 인증 결과에서 확인된 워크스페이스와 봇 사용자 ID를 사용하고, 입력한 App ID가 인증 결과와 충돌하면 거부한다. 기존 설정과 내용이 같으면 재사용하며, 다른 설정으로 조용히 덮어쓰지 않는다. 실제 값은 콘솔에 다시 출력하지 않는다.

Slack 웹 주소 끝의 `C`로 시작하는 값은 현재 채널 ID다. User ID는 Slack 프로필의 멤버 ID 복사 기능으로 확인한다.

- Slack 워크스페이스 ID 안내: https://slack.com/help/articles/221769328-Locate-your-Slack-URL-or-ID

준비 상태는 다음 명령으로 확인한다.

    python scripts/check_slack_setup.py

이 명령은 ID 형식, 허용 목록과 Token의 존재 및 접두사만 확인한다. Token 값을 콘솔이나 결과 파일에 출력하지 않으며 Slack 네트워크에도 접속하지 않는다. 2026-09-14 실제 개인 설정은 이 검사를 통과했다.

Token을 입력한 뒤 실제 인증 상태는 다음 명령으로 확인한다.

    python scripts/verify_slack_tokens.py

Bot Token은 별도 Scope가 필요 없는 Slack 공식 `auth.test`로 인증하고, App Token은 `apps.connections.open` 응답으로 Socket Mode 사용 가능 여부를 확인한다.

- `auth.test`: https://docs.slack.dev/reference/methods/auth.test/
- `connections:write`: https://docs.slack.dev/reference/scopes/connections.write/

요청은 `https://slack.com/api/`의 두 허용 메서드에만 POST로 전송하며 외부 리디렉션을 따르지 않는다. Token은 Authorization 헤더로만 보내고, 응답의 Token과 임시 WebSocket URL은 출력하거나 저장하지 않는다. 비밀정보가 없는 인증 결과만 `private-data/slack-auth/`에 저장한다. 2026-09-14 실제 Bot Token 인증과 Socket Mode URL 발급 가능 여부도 확인했다.

## 9. 현재 보안 경계와 다음 단계

HTTP Request URL 방식은 Slack Signing Secret으로 요청 서명을 반드시 확인해야 한다.

- Slack 요청 서명 검증: https://docs.slack.dev/authentication/verifying-requests-from-slack

현재 로컬 변환 결과의 `network_request_verified`는 항상 `false`이며 `execution_status`도 `not_executed`다. 따라서 실제 Slack 요청을 이 함수에 직접 넣어 실행하면 안 된다.

다음 단계에서는 Socket Mode 연결을 별도 어댑터로 만들고 다음 순서로 처리한다.

1. 환경 변수에서 App Token과 Bot Token을 읽는다.
2. Slack 연결이 인증한 이벤트만 현재 변환기에 전달한다.
3. 요청을 먼저 확인 응답한 뒤 내부 작업을 분리 실행한다.
4. 완료 또는 실패 결과를 원래 채널에 보낸다.
5. 동일 `event_id` 재전송은 다시 분석하지 않는다.
