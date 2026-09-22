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

현재 지원하는 사용자 입력은 일곱 가지다.

    <@봇사용자ID> 다음 공고 찾아줘
    <@봇사용자ID> 프로필 분석해줘 + 첨부파일 1개
    <@봇사용자ID> 프로필 초안 보여줘
    <@봇사용자ID> 프로필 검토 시작
    <@봇사용자ID> 맞아
    <@봇사용자ID> 제외해줘
    <@봇사용자ID> 프로필 변경 검토 시작

첨부파일 1개와 봇 호출만 보내도 프로필 자료 입력으로 인식한다. 공고 검색 명령은 공백과 봇 호출 위치만 정규화하며 비슷한 다른 문장을 Agent가 같은 뜻이라고 임의로 추정하지 않는다.

    command_name: "find_next_job"
    action: "analyze_next_greenhouse_review"

이 동작은 기존 `scripts/analyze_next_greenhouse_review.py`의 “검토 큐에서 다음 공고 1건 분석” 기능을 가리킨다. 로컬 합성 이벤트 변환기는 동작 이름만 식별하고 실행하지 않으며, 실제 Socket Mode 수신기만 허용된 동작을 고정 인자 프로세스로 실행한다.

프로필 자료 입력은 이번 단계에서 다음 메타데이터만 검증한다.

- Slack 파일 ID
- 경로 문자가 없는 파일명
- `.txt`, `.md`, `.pdf`, `.docx` 확장자와 대응 MIME 형식
- 1바이트 이상 10MB 이하 크기
- PDF·DOCX의 `hosted`, TXT·Markdown의 `hosted` 또는 `snippet` 저장 방식

검증된 요청의 상태는 `input_validated`, 요청 기록 시점의 처리 상태는 `metadata_validated_download_not_started`다. 파일 내용과 `url_private` 다운로드 URL은 요청 기록에 저장하지 않는다. 실제 수신기는 별도 다운로드 어댑터로 파일 정보를 다시 조회하고 비공개 문서 저장소에 넣는다. 외부 드라이브 파일과 Slack Connect에서 추가 확인이 필요한 파일은 현재 지원하지 않는다.

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
- `files:read`: 사용자가 첨부한 파일 정보 조회와 인증 다운로드
- `app_mention`: 구독 이벤트
- `connections:write`: manifest의 Bot Token Scope가 아니라 별도로 만드는 Socket Mode App Token의 권한

첨부파일 메타데이터 검증은 `app_mention` 이벤트의 `files` 배열을 사용한다. 실제 다운로드 직전에 `files.info`로 동일 파일인지 다시 확인하고, Slack의 인증이 필요한 비공개 URL에 Bearer 인증 헤더를 붙여 내려받는다. 공개 URL로 전환하거나 외부 호스트 리디렉션을 허용하지 않는다.

기존에 설치한 앱은 manifest 파일 변경만으로 권한이 갱신되지 않는다. `OAuth & Permissions`의 Bot Token Scopes에 `files:read`를 추가한 뒤 워크스페이스에 앱을 다시 설치하거나 재승인해야 한다. 실제 승인 전까지 다운로드 기능은 사용할 수 없다.

2026-09-15 개인 워크스페이스에서 `files:read` 재승인, 기존 파일의 `files.info` 조회와 새 DOCX 첨부파일의 인증 다운로드·비공개 저장을 확인했다. 요청과 저장 manifest에는 파일 내용과 다운로드 URL을 남기지 않았고 수신기 오류는 없었다. 저장 직후 TXT·Markdown·DOCX 로컬 추출을 실행하며 Slack에는 후보 원문 대신 섹션별 개수와 기간·수치·실행·기술명 언급의 근거 신호 개수만 보낸다. 이 응답은 최종 이력서 분석이 아니라 1차 문단 분류임을 표시하고, 인식 영역이 하나뿐이면 추가 구조화가 필요하다고 경고한다. 근거 신호는 실제 경력 사실, 성과 또는 기술 숙련도로 확정하지 않는다. PDF는 저장 성공과 본문 추출 미지원을 구분한다.

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

매칭 규칙, 분석 파이프라인 또는 프로필이 바뀌어 기존 검토 큐가 오래된 경우 분석 명령의 명시적 `검토 큐를 다시 생성해야 함` 오류만 자동 복구한다. 고정된 큐 생성 스크립트로 새 큐를 만든 뒤 분석을 한 번만 재시도한다. 다른 오류는 자동 재시도하지 않고 고정 실패 안내를 반환한다.

실제 이벤트는 `network_request_verified: true`, 합성 로컬 이벤트는 `local_validation_only: true`로 구분한다. Slack 명령 요청 자체의 `execution_status`는 라우팅 시점 기록이므로 `not_executed`를 유지하고, 실제 분석 성공·실패는 기존 별도 실행 이력에 저장한다. 메시지 원문은 저장하지 않는다.

성공 응답은 회사·공고명, 검증된 HTTPS 원문 링크, 공고 정보 충분도, `RECOMMEND`·`HOLD`·`NOT_RECOMMEND` 추천 상태와 근거를 포함한다. 비교 결과는 확인된 일치, 확인된 부족 또는 불일치, 공고에서 확인할 수 없는 정보, 비교를 위해 추가 확인할 정보로 나눈다. 각 영역은 최대 2~5개로 제한한다. 외부 공고에서 온 `<`, `>`, `&`는 Slack 제어 문자열로 해석되지 않도록 변환한다. 로컬 저장 경로, 원본 표준 출력과 오류 내용은 Slack에 보내지 않는다.

프로필 직무 근거와 지역·고용 조건을 함께 만족하는 미분석 후보가 없으면 이를 실행 실패로 처리하지 않는다. `no_eligible_candidate` 실행 이력을 남기고 Slack에는 현재 조건에 맞는 새 공고가 없다는 고정 안내와 큐 상태를 전달한다. 큐 상태는 분석 완료, 미분석이지만 조건 불일치, 현재 분석 가능 개수를 구분한다. 이 경우 공고 상세 API를 호출하거나 분석 파일을 만들지 않는다.

첫 큐 검사에서 분석 가능한 후보가 없으면 등록된 Greenhouse 공식 보드 목록을 한 번 갱신하고 새 검토 큐를 만든 뒤 후보를 다시 검사한다. 목록 갱신은 `--discovery-only` 모드로 실행해 공고 상세 분석을 소비하지 않는다. 갱신 후에도 후보가 없으면 공식 채용 소스를 방금 갱신했지만 새 분석 후보가 없다고 알린다. 목록 갱신이 실패하면 기존 빈 큐 결과는 유지하되 갱신 실패를 구분하고 원격 오류 내용은 Slack에 노출하지 않는다.

2026-09-15 실제 지정 채널에서 보낸 이벤트 수신, 허용 검사, 명령 변환과 스레드 답변 표시를 사용자가 확인했다. 빈 큐에서 Greenhouse 공식 소스를 자동 갱신한 뒤 정확한 큐 상태를 표시하는 동작도 사용자가 확인했다.

### 9.1 프로필 분석 초안 표시 경계

검증된 `needs_review` 프로필 분석 초안을 Slack에 표시할 때는 경력 근거, 성과 근거, 기술 사용 근거와 추가 확인 질문의 개수만 전달한다. 후보 문장, 역할명, 회사명, 기술명, 후보 ID, 초안 ID, 공급자 이름과 로컬 저장 경로는 응답에 포함하지 않는다.

초안 요약은 내부 분석 배열과 항목 수가 일치하고, 공급자 출력 검증이 완료됐으며, 아직 프로필에 반영되지 않은 비공개 초안에만 생성된다.

`프로필 초안 보여줘` 명령은 개인용 MVP의 비공개 저장소에서 가장 최근 검증된 추출 결과를 선택하고, 같은 추출 ID에 속한 최신 검증 초안을 이 포맷터로 전달한다. 초안이 없으면 문단 분류까지만 완료된 상태라고 안내하며 새 분석 결과를 임의로 만들지 않는다. 같은 Slack 스레드에 답변하고 메시지 원문은 명령 요청 기록에 저장하지 않는다.

현재 연결 키는 허용 사용자가 본인 1명인 개인용 MVP라는 전제 아래 비공개 저장소의 최신 검증 추출 결과다. 여러 사용자를 허용하는 단계에서는 Slack 사용자 ID와 추출 ID를 연결하는 별도 비공개 인덱스로 교체해야 한다. 실제 TXT·Markdown·DOCX 첨부는 추출 직후 외부 전송 없는 로컬 검증 초안을 자동 생성하며 Slack 응답에는 항목 수와 다음 검토 명령만 표시한다. 실제 사용자 문서의 외부 전송 동의 기록은 구현했지만, 동의된 내용을 외부 공급자에 보내는 단계는 연결하지 않았다.

### 9.2 프로필 분석 항목 한 건 표시

`프로필 검토 시작` 명령은 최신 검증 초안에서 경력 근거, 성과 근거, 기술 사용 근거, 추가 확인 질문 순서로 첫 항목 한 건만 표시한다. 한 번에 전체 이력서 파생 내용을 보내지 않는다.

항목 응답에는 사람이 확인할 구조화 내용, AI 판단 신뢰도, 전체 항목 중 현재 위치와 사람이 읽을 항목 종류만 포함한다. 후보 ID, 초안 ID, 추출 ID, 공급자, 모델과 로컬 저장 경로는 포함하지 않는다. 분석 내용의 `<`, `>`와 `&`는 Slack 멘션이나 제어 문자열로 실행되지 않게 변환하며 줄바꿈은 한 줄 공백으로 정규화한다.

항목을 표시할 때 워크스페이스, 채널, 사용자, 스레드와 대상 항목 식별자만 비공개 검토 세션에 저장한다. 메시지 원문, 분석 문장과 후보 문장은 세션에 복제하지 않는다. 표시된 스레드 안에서 같은 허용 사용자가 `맞아`라고 답하면 `approve`, `제외해줘`라고 답하면 `reject` 결정을 기존 불변 검토 기록으로 저장한다. 스레드 밖 답변, 다른 사용자·채널·스레드의 답변과 이미 결정된 세션은 항목에 연결하지 않는다.

결정이 저장된 항목은 다음 `프로필 검토 시작`에서 건너뛴다. 승인·거부 기록의 `profile_updated`는 계속 `false`이며 이 단계에서는 개인 프로필과 공고 검색 조건을 변경하지 않는다. 실제 사용자 문서의 분석 초안이 없으면 문단 분류까지만 완료됐다고 안내한다. 자유 형식 `수정` 답변은 분석 내용 검증 계약이 별도로 필요하므로 아직 지원하지 않는다.

### 9.3 프로필 변경 매핑 항목 한 건 표시

`프로필 변경 검토 시작` 명령은 최신 추출 결과와 분석 초안의 최신 결정을 사용해 현재 프로필 기준의 비파괴 변경 제안을 만들고, 매핑 확인이 필요한 첫 항목 한 건만 표시한다. 분석 항목 검토가 끝나지 않았으면 먼저 `프로필 검토 시작`을 완료하도록 안내한다.

- 경력·성과 근거에는 구조화 내용과 기존 프로필의 허용 경력 ID, 역할 및 기간을 표시한다.
- 새 기술 근거에는 기술명, 사용 근거와 `none`, `exposure`, `learning`, `basic`, `project`, `work`의 허용 숙련도만 표시한다.
- 내부 제안 ID, 검토 ID, 후보 ID와 로컬 경로는 공개 응답에 포함하지 않는다.
- 제안 내용의 Slack 제어 문자열은 무해화한다.
- 기존 기술의 근거 추가처럼 추가 매핑이 필요 없는 항목은 건너뛴다.

항목을 표시할 때 워크스페이스, 채널, 사용자, 스레드, 제안 ID, 변경 항목 ID와 허용값만 비공개 매핑 세션에 저장한다. 메시지 원문, 분석 문장과 후보 문장은 세션에 복제하지 않는다.

- 경력·성과 항목은 같은 스레드의 `경력 <경력ID>` 답변만 받는다.
- 새 기술 항목은 같은 스레드의 `기술수준 <숙련도>` 답변만 받는다.
- 현재 프로필에 존재하지 않는 경력 ID와 세션에 표시되지 않은 값은 거부한다.
- 다른 사용자·채널·스레드의 답변과 이미 결정된 세션은 항목에 연결하지 않는다.
- 결정이 저장된 항목은 다음 `프로필 변경 검토 시작`에서 건너뛴다.

선택 기록에는 결정 종류와 선택값만 저장하고 분석 내용을 복제하지 않는다. 기록의 `profile_updated`는 `false`이며 실제 개인 프로필과 공고 검색 조건은 아직 변경하지 않는다.

### 9.4 프로필 최종 변경안 표시

모든 매핑 선택이 저장된 뒤 `프로필 최종 검토` 명령은 자동 준비된 기존 기술 근거 추가와 사용자가 선택한 경력·숙련도 매핑을 하나의 불변 최종 변경안으로 합친다.

- 기준 프로필 내용 지문이 변경 제안과 다르면 최종 변경안을 만들지 않는다.
- 매핑이 필요한 항목에 선택 기록이 하나라도 없으면 `프로필 변경 검토 시작`을 먼저 완료하도록 안내한다.
- 경력·성과의 대상 경력 ID와 새 기술의 숙련도를 최종 변경 내용에 확정한다.
- 새 기술의 `skill_id`는 정규화된 기술명으로 만들고 현재 프로필 또는 같은 변경안과 충돌하면 거부한다.
- Slack에는 변경 종류별 개수, 대상 경력·기술과 근거 요약을 표시하고 내부 제안·검토 ID는 숨긴다.
- Slack 한 메시지의 안전한 표시 한도를 넘으면 축약 승인으로 진행하지 않고 오류로 중단한다.

최종 변경안은 Git에서 제외된 비공개 저장소에 저장하며 `profile_updated`는 `false`다. 항목을 표시할 때 워크스페이스, 채널, 사용자, 스레드와 최종 변경안 ID만 전용 비공개 세션에 저장한다.

같은 스레드에서 `최종 승인`이라고 답하면 내용이 없는 명시적 승인 기록을 먼저 저장하고, 기준 프로필 지문을 다시 확인한 뒤 원본과 분리된 새 비공개 프로필 버전을 만든다. `최종 취소`는 거부 기록과 미적용 이력만 만들고 새 프로필을 생성하지 않는다. 다른 사용자·채널·스레드의 답변과 이미 결정된 세션은 연결하지 않는다.

적용 결과는 경력 수행 근거 추가, 새 성과 객체 추가, 기존 기술 근거 추가와 새 기술 추가를 지원한다. 적용 이력에는 프로필 내용을 복제하지 않고 변경 ID, 대상 ID와 동작만 기록한다. 새 프로필 버전은 별도 디렉터리에 저장하며 기준 프로필 파일을 덮어쓰지 않는다.

승인 적용과 같은 시각에 적용 ID와 새 프로필 내용 지문만 담은 불변 활성화 기록을 만든다. 이후 Slack의 다음 공고 분석이 호출하는 공식 소스 갱신, 검토 큐 생성과 상세 분석 스크립트는 명시적 프로필 경로가 없으면 최신 활성화 기록을 선택하고 고정된 비공개 적용 디렉터리의 프로필을 다시 검증해 사용한다. 활성화 기록이 없을 때만 공개 예제 프로필을 사용하며, 기록이 있지만 대상 파일이나 지문이 잘못된 경우에는 예제로 되돌아가지 않고 실패한다.

선택된 프로필에서 목표 직무, 실제 근거가 있는 기술과 명시된 선호만 사용해 검색 계획을 다시 만든다. 경력 연수, 재택 선호와 보유하지 않은 기술을 추정하지 않으며 낮은 선호는 순위 하향에만 사용한다. 따라서 최종 승인 뒤의 다음 `다음 공고 찾아줘`부터 새 활성 프로필과 같은 근거를 사용하는 검색 계획이 적용된다.

### 9.5 외부 AI 분석 동의 경계

외부 AI 분석 동의·거부 기록과 실행 경계가 연결되어 있다. 실제 TXT·Markdown·DOCX는 먼저 외부 전송 없는 로컬 초안을 만들고, Gemini 분석이 활성화된 수신기는 외부 전송 범위와 경력·회사·프로젝트 정보 포함 가능성을 안내한 뒤 해당 문서 스레드에서 동의 또는 거부를 받는다.

동의 세션은 워크스페이스, 채널, 사용자, 스레드, 추출 결과 ID, 최소 공급자 요청의 SHA-256 지문, 공급자와 모델에 묶인다. 결정 기록도 정확한 세션·사용자·스레드를 포함하며 후보 문장, 파일 내용과 메시지 원문을 복제하지 않는다. 다른 사용자·채널·스레드의 답변과 스레드 밖 답변은 연결하지 않고, 같은 문서·공급자·모델의 가장 최신 세션이 승인 상태일 때만 외부 호출을 실행한다.

Gemini 무료 등급은 입력과 응답이 제품·모델 개선과 사람 검토에 사용될 수 있다. 기본값은 전송 금지이며 현재 개인용 개발 테스트에서는 사용자가 해당 문서의 이 조건을 이해하고 명시적으로 승인한 경우에만 최소 후보 텍스트를 보낸다. 실제 서비스 전환 전에는 유료 데이터 처리와 보존 조건, 동의 UX를 다시 결정한다.

## 10. 현재 보안 경계와 다음 단계

HTTP Request URL 방식은 Slack Signing Secret으로 요청 서명을 반드시 확인해야 한다.

- Slack 요청 서명 검증: https://docs.slack.dev/authentication/verifying-requests-from-slack

HTTP Request URL 방식의 이벤트를 현재 변환기에 직접 넣으면 안 된다. 이 경로는 Slack Signing Secret 검증을 구현하지 않았기 때문이다. 실제 네트워크 이벤트는 인증된 Socket Mode 연결을 통해서만 전달한다.

2026-09-15 실제 Slack 명령으로 공고 분석과 상세 요약 표시를 확인했다. 프로필 근거가 약한 일반 직무 후보와 채용관심등록 공고를 제외한 최신 큐에서는 현재 자동 상세 분석 가능한 새 후보가 없다.

궁극적인 Slack Agent 흐름을 완성하기 위한 다음 우선순위는 실제 첨부부터 승인된 프로필 기반 공고 추천까지의 전체 재검증이다.

1. 사용자가 이력서, 포트폴리오, 경력기술서 또는 직무분석표 한 개를 첨부한다.
2. 파일을 비공개 원본 저장소에 가져오고 저장 직후 검토용 프로필 후보를 만든다.
3. 외부 전송 없는 로컬 초안을 만들고, 사용자가 승인하면 Gemini 분석 초안을 추가 생성한다.
4. Agent가 분석 결과를 대화형 요약으로 보여주고 필요한 모호점만 질문한 뒤 새 개인 프로필을 활성화한다.
5. 활성 프로필에서 검색 계획을 다시 만들고 공고 발견·분석과 사용자 피드백 기록으로 이어간다.
