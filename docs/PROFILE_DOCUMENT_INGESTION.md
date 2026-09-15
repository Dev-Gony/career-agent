# Profile Document Ingestion

## 1. 목적

Slack 또는 Telegram에서 이력서, 경력기술서와 포트폴리오를 받아 재사용할 수 있는 비공개 문서 입력·저장 경계를 정의한다.

이 단계는 원본을 안전하게 보존하는 기능이다. 문서 내용을 해석하거나 `user_profile`을 자동 변경하지 않는다.

## 2. 입력

문서 종류 `document_kind`는 다음 중 하나다.

- `resume`: 이력서
- `career_history`: 경력기술서
- `portfolio`: 포트폴리오
- `other`: 그 밖의 경력 관련 자료

현재 로컬 명령이 허용하는 확장자와 검증은 다음과 같다.

| 확장자 | 형식 | 최소 검증 |
| --- | --- | --- |
| `.txt` | `plain_text` | UTF-8 디코딩, null 문자 없음 |
| `.md` | `markdown` | UTF-8 디코딩, null 문자 없음 |
| `.pdf` | `pdf` | `%PDF-` 파일 서명 |
| `.docx` | `docx` | ZIP 구조와 필수 문서 항목 |

파일 크기는 최대 10MB다. 확장자만 맞고 최소 형식 검증에 실패한 파일은 저장하지 않는다.

## 3. 저장 구조

기본 저장 경로는 Git에서 제외된 `private-data/profile-documents/`다.

    private-data/profile-documents/
      profile-document-resume-0123456789abcdef0123/
        manifest.json
        original.pdf

문서 ID는 문서 종류와 원본 내용의 SHA-256 해시 앞 20자로 만든다. 같은 종류와 같은 내용은 같은 문서 ID가 되므로 Slack 재시도나 중복 실행에서 원본을 다시 쓰지 않는다.

`manifest.json`에는 다음 메타데이터만 저장한다.

- 문서 ID와 가져온 시각
- 문서 종류와 입력 출처 유형
- 원래 파일명, 검증된 형식과 비공개 저장 파일명
- 바이트 크기와 전체 내용 SHA-256
- 처리 상태 `stored_unparsed`
- 개인정보 포함 가능성과 Git 추적 금지 표시

원본의 절대 경로와 문서 내용은 manifest에 복제하지 않는다.

## 4. Slack 첨부파일 입력 경계

Slack의 `app_mention` 이벤트에 포함된 `files` 배열에서 파일 한 개의 메타데이터를 검증한다.

    @career_break 프로필 분석해줘 + 첨부파일 1개

현재는 Slack 파일 ID, 파일명, 확장자, MIME 형식, 크기와 `hosted` 여부만 확인한다. 메시지 원문, 파일 내용과 인증이 필요한 다운로드 URL은 `private-data/slack-command-requests/`에 저장하지 않는다. 검증 성공 응답에도 파일명을 다시 노출하지 않는다.

파일 내용 다운로드는 아직 하지 않는다. 다음 단계에서 최소 권한 `files:read`를 추가하고 사용자가 앱 권한을 다시 승인한 뒤, Bot Token을 Authorization 헤더로 보내는 Slack 인증 다운로드만 허용한다.

## 5. 로컬 파일 실행

    python scripts/import_profile_document.py --file "C:\path\resume.pdf" --kind resume

정상 저장이면 문서 종류, 형식, 크기, 처리 상태와 비공개 manifest 경로만 출력한다. 같은 문서를 다시 넣으면 `동일 사용자 문서 재사용`으로 표시한다.

## 6. 개인정보와 실행 경계

- 원본과 manifest는 공개 저장소에 커밋하지 않는다.
- 파일 내용을 콘솔이나 작업일지에 출력하지 않는다.
- 문서를 코드로 실행하지 않는다.
- 이 단계에서는 외부 AI 또는 문서 처리 서비스로 전송하지 않는다.
- 공개 테스트에는 합성 텍스트와 최소 DOCX 컨테이너만 사용한다.

## 7. 현재 한계

- PDF와 DOCX의 전체 무결성 검사나 악성 파일 검사는 하지 않는다.
- 이미지 기반 PDF의 OCR을 하지 않는다.
- UTF-8 TXT와 Markdown만 제목 기반 프로필 후보 추출을 지원한다.
- PDF와 DOCX의 본문 텍스트를 추출하지 않는다.
- 추출 후보의 승인·거부, 승인 후보 갱신안, 기술 후보 매핑, 세부정보 확인, 완성된 기술 추가안, 최종 승인·거부와 승인 기술의 새 프로필 버전 적용을 지원한다. 기술 이외의 프로필 영역 반영은 아직 지원하지 않는다.
- Slack 첨부파일 메타데이터 검증은 지원하지만 파일 다운로드 어댑터는 아직 없다.
- Telegram 첨부파일 입력은 아직 없다.

텍스트 추출 결과 구조와 개인정보 제외 기준은 `docs/PROFILE_EXTRACTION_SCHEMA.md`에서 정의한다.
