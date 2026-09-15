# Slack Interface

## 1. 목적

Slack 채널에서 사용자가 Career Agent를 호출하는 첫 입력 경계를 정의한다. 실제 Slack 앱의 Token 인증, 개인 허용 목록 설정과 Socket Mode 연결을 완료했다. 합성 또는 실제 `app_mention` 이벤트를 검증하고 허용된 내부 동작 요청으로 변환하며, 지원 명령은 기존 다음 공고 1건 분석에 연결된다.

    Slack app_mention 예제
    -> 워크스페이스·앱·사용자·채널 검증
    -> 명령 식별
    -> 허용된 내부 동작 실행
    -> 같은 Slack 스레드에 결과 전달

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

현재 지원하는 사용자 입력은 두 가지다.

    <@봇사용자ID> 다음 공고 찾아줘
    <@봇사용자ID> 프로필 분석해줘 + 첨부파일 1개

첨부파일 1개와 봇 호출만 보내도 프로필 자료 입력으로 인식한다. 공고 검색 명령은 공백과 봇 호출 위치만 정규화하며 비슷한 다른 문장을 Agent가 같은 뜻이라고 임의로 추정하지 않는다.

    command_name: "find_next_job"
    action: "analyze_next_greenhouse_review"

이 동작은 기존 `scripts/analyze_next_greenhouse_review.py`의 “검토 큐에서 다음 공고 1건 분석” 기능을 가리킨다. 로컬 합성 이벤트 변환기는 동작 이름만 식별하고 실행하지 않으며, 실제 Socket Mode 수신기만 허용된 동작을 고정 인자 프로세스로 실행한다.

프로필 자료 입력은 이번 단계에서 다음 메타데이터만 검증한다.

- Slack 파일 ID
- 경로 문자가 없는 파일명
- `.txt`, `.md`, `.pdf`, `.docx` 확장자와 대응 MIME 형식
- 1바이트 이상 10MB 이하 크기
- Slack에 직접 올린 `hosted` 파일인지 여부

검증된 요청의 상태는 `input_validated`, 처리 상태는 `metadata_validated_download_not_started`다. 파일 내용과 `url_private` 다운로드 URL은 읽거나 요청 기록에 저장하지 않는다. 외부 드라이브 파일과 Slack Connect에서 추가 확인이 필요한 파일은 현재 지원하지 않는다.

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

프로필 자료 입력이면 다음 객체가 추가된다.

    profile_document:
      file_id: "F01234567"
      filename: "resume.pdf"
      extension: ".pdf"
      mimetype: "application/pdf"
      size_bytes: 1024
      source_type: "slack_attachment"
      processing_status: "metadata_validated_download_not_started"

이때 metadata의 `contains_file_content`와 `contains_download_url`은 모두 `false`여야 한다.

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

현재 첨부파일 메타데이터 검증은 `app_mention` 이벤트의 `files` 배열만 사용하고 별도 파일 API를 호출하지 않는다. 다음 다운로드 단계에는 Bot Token의 `files:read` 권한이 필요하며, 권한을 manifest에 추가한 뒤 사용자가 앱을 다시 승인해야 한다. 파일은 Slack의 인증이 필요한 `url_private`에서 Bearer 인증 헤더로만 내려받고 공개 URL로 전환하지 않는다.

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

## 9. 실제 Socket Mode 수신

공식 Slack Bolt SDK를 설치하고 로컬 수신기를 실행한다.

    python -m pip install -r requirements.txt
    python scripts/run_slack_socket.py

지정 채널에서 다음처럼 봇을 호출한다.

    @career_break 다음 공고 찾아줘

수신기는 Bolt가 전달한 `app_mention` 전체 이벤트를 기존 변환기로 검증한다. 허용된 워크스페이스·앱·사용자·채널과 지원 명령이면 원래 메시지의 스레드에 분석 시작을 먼저 알리고 다음 공고 1건만 분석한다. 같은 `event_id`가 재전송되면 저장 결과를 재사용하고 분석과 응답을 중복 실행하지 않는다. 허용되지 않은 사용자나 채널에는 응답하지 않는다.

실제 이벤트는 `network_request_verified: true`, 합성 로컬 이벤트는 `local_validation_only: true`로 구분한다. Slack 명령 요청 자체의 `execution_status`는 라우팅 시점 기록이므로 `not_executed`를 유지하고, 실제 분석 성공·실패는 기존 별도 실행 이력에 저장한다. 메시지 원문은 저장하지 않는다.

성공 응답은 회사·공고명, 검증된 HTTPS 원문 링크, 지원 판단과 근거, 확인된 강점과 프로젝트 증거, 확인된 부족, 우선 확인 질문, 다음 행동과 남은 큐를 포함한다. 각 영역은 최대 2~3개로 제한한다. 외부 공고에서 온 `<`, `>`, `&`는 Slack 제어 문자열로 해석되지 않도록 변환한다. 로컬 저장 경로, 원본 표준 출력과 오류 내용은 Slack에 보내지 않는다.

프로필 직무 근거와 지역·고용 조건을 함께 만족하는 미분석 후보가 없으면 이를 실행 실패로 처리하지 않는다. `no_eligible_candidate` 실행 이력을 남기고 Slack에는 현재 조건에 맞는 새 공고가 없다는 고정 안내와 큐 상태를 전달한다. 이 경우 공고 상세 API를 호출하거나 분석 파일을 만들지 않는다.

2026-09-15 실제 지정 채널에서 보낸 이벤트 수신, 허용 검사, 명령 변환과 스레드 답변 표시를 사용자가 확인했다.

## 10. 현재 보안 경계와 다음 단계

HTTP Request URL 방식은 Slack Signing Secret으로 요청 서명을 반드시 확인해야 한다.

- Slack 요청 서명 검증: https://docs.slack.dev/authentication/verifying-requests-from-slack

HTTP Request URL 방식의 이벤트를 현재 변환기에 직접 넣으면 안 된다. 이 경로는 Slack Signing Secret 검증을 구현하지 않았기 때문이다. 실제 네트워크 이벤트는 인증된 Socket Mode 연결을 통해서만 전달한다.

2026-09-15 실제 Slack 명령으로 공고 분석과 상세 요약 표시를 확인했다. 프로필 근거가 약한 일반 직무 후보와 채용관심등록 공고를 제외한 최신 큐에서는 현재 자동 상세 분석 가능한 새 후보가 없다.

궁극적인 Slack Agent 흐름을 완성하기 위한 다음 우선순위는 첨부파일 수신이다.

1. 사용자가 이력서, 포트폴리오, 경력기술서 또는 직무분석표 한 개를 첨부한다.
2. 파일을 비공개 원본 저장소에 가져오고 검토용 프로필 후보를 만든다.
3. 사용자가 후보를 확인한 뒤 새 개인 프로필과 검색 계획을 생성한다.
4. 이후 사용자 판단 입력을 기존 비공개 피드백 기록에 연결한다.
