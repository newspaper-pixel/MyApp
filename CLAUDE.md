# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 상태

Streamlit으로 만드는 가벼운 쇼핑 리스트 웹앱입니다(아이템 추가 · 수정 · 삭제 · 체크). **4단계(Playwright 검토)에서 찾은 버그 10개를 고쳤습니다.** 수정 후 수용 기준과 버그별 재테스트는 통과했습니다. 4단계에서 정상이었던 예외 상황(같은 이름 아이템, 가운데 삭제, 특수문자·긴 이름, 새로고침 유지 등)은 수정 후 아직 다시 돌리지 않았습니다. 이 확인이 끝나면 다음은 배포(PRD 9장)입니다.

- `PRD.md`: 요구사항의 기준 문서. 기능 요구사항(FR-1~6), 데이터 모델, 수용 기준(10장)이 여기 있습니다.
- `PROMPTS.md`: 4단계 개발 프롬프트(1 뼈대 → 2 기능 → 3 UI → 4 Playwright 검토). 사용자는 이 순서대로 한 단계씩 진행하므로, 요청받은 단계의 범위를 넘어 다음 단계 작업까지 하지 마세요. 예를 들어 3단계(UI)에서는 기능 로직을 바꾸지 않습니다.
- `쇼핑리스트앱.txt`: 사용자의 원본 요청 메모.

코드를 만들거나 고칠 때는 PRD와 어긋나지 않게 하고, 요구사항이 바뀌면 `PRD.md`도 함께 고치세요.

## 명령어

프로젝트 가상환경은 `.venv`입니다. 전역 Python(3.14)에는 streamlit이 설치되어 있지 않습니다.

```bash
python -m venv .venv && .venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/streamlit run app.py
.venv/Scripts/streamlit run app.py --server.headless true --server.port 8501   # Playwright 테스트용
```

`requirements.txt`는 `streamlit>=1.66,<2`입니다. `st.container(key=)`, `[theme.light]`/`[theme.dark]` 같은 최신 기능을 쓰므로 버전을 낮추지 마세요. 실제로 확인한 버전은 1.66.1입니다.

테스트 프레임워크나 린터는 정하지 않았습니다. 검증은 Playwright MCP로 실행 중인 앱을 직접 조작해서 합니다(PROMPTS.md 4단계). 해 보면서 알게 된 점:
- 테스트 전에 `data/items.json`을 백업하고 끝나면 복원하세요. 사용자가 열어 둔 탭에서 넣은 실제 데이터가 있을 수 있습니다.
- 클릭할 때마다 다시 실행이 끝날 때까지 기다려야 합니다(`stStatusWidget`에 "Running"이 사라질 때까지 기다린 뒤 0.5초 정도 더).
- 아이템 행 안에는 크기가 0인 숨은 버튼(툴팁용 복제본)이 있습니다. 위치나 크기를 잴 때는 보이는 요소만 고르세요.
- 추가 폼에는 1.5초 연속 제출 보호(`DOUBLE_SUBMIT_WINDOW`)가 있습니다. 추가한 직후의 빈 제출이나 같은 이름 제출은 무시되니, 테스트 사이에 1.6초 이상 기다리세요.
- 서버는 Bash에서 프로세스 명령줄로 찾아 끄지 마세요. 그 Bash 셸도 같은 문자열에 걸려 함께 종료됩니다. PowerShell 도구에서 `python.exe`/`streamlit.exe` 프로세스만 골라 끄세요.
- `.streamlit/config.toml`을 바꿨으면 서버를 재시작해야 적용됩니다.

## 아키텍처

- **단일 `app.py`**이고, 표준 라이브러리와 `streamlit`만 사용합니다.
- **상태:** `st.session_state["items"]`(아이템 dict 리스트: `id`, `name`, `quantity`, `checked`, `created_at`)와 `st.session_state["editing_id"]`(한 번에 하나만 편집)를 씁니다. `items`는 원본이 아니라 캐시입니다. `init_state()`가 실행될 때마다 저장소에서 다시 읽어 다른 탭이나 기기의 변경을 반영합니다.
- **저장소 추상화:** 저장 I/O는 `load_items()` / `save_items()`에서만 합니다. 현재 대상은 `data/items.json`이고(gitignore 대상), 나중에 외부 DB(Google Sheets/Supabase, `st.secrets`)로 바꿀 수 있어야 하므로 UI 코드에서 파일을 직접 다루지 마세요.
  - `load_items()`는 아이템마다 `normalize_item()`으로 형식을 맞추고, 복구할 수 없거나 id가 중복된 아이템은 건너뜁니다. JSON이 깨졌으면 파일을 `items.broken-<시각>.json`으로 옮깁니다.
  - `save_items()`는 실패하면 `SaveError`를 던집니다.
- **변경 흐름:** 상태 변경 함수(`add_item`, `update_item`, `delete_item`, `set_checked`, `clear_checked`)는 모두 `commit(change)`를 거칩니다. `commit`은 락을 잡고, 저장소를 다시 읽고, `change(items)`를 적용한 뒤 저장합니다. 이렇게 해야 탭 여러 개가 서로의 변경을 덮어쓰지 않으니, session_state의 리스트를 직접 고쳐 저장하는 코드를 새로 만들지 마세요.
- **입력 검사:** 입력값은 `validate()` 한 곳에서 검사합니다(이름 필수, 수량 `MIN_QTY`~`MAX_QTY`). `number_input`에 `min_value`/`max_value`를 주면 Streamlit이 영어 툴팁만 띄우고 제출을 조용히 막으니 주지 마세요. 한계가 하나 있습니다. 약 9천조(JS 안전 정수)를 넘는 수는 Streamlit 화면 쪽에서 먼저 막아서 한국어 안내가 뜨지 않습니다.
- **추가 폼:** `clear_on_submit`을 쓰지 않습니다. 쓰면 입력이 잘못됐을 때도 이름이 지워집니다. 추가에 성공했을 때만 `on_add_submit`이 `add_name` / `add_qty`를 비웁니다. 콜백에서 위젯 값을 바꾸므로 `add_qty`의 기본값은 `value=` 대신 `st.session_state.setdefault`로 줍니다. 둘 다 주면 Streamlit 경고가 뜹니다.
- **사용자 안내 문구:** `EMPTY_NAME_MSG`, `QTY_MSG`, `SAVE_FAILED_MSG`, `GONE_MSG`는 파일 맨 위 상수에 모아 두었습니다. 다른 탭에서 이미 삭제된 아이템을 체크·수정·삭제하면 `GONE_MSG` 알림을 띄우고 아이템을 되살리지 않습니다.

## Streamlit 주의사항

- 위젯 key는 반드시 아이템 `id` 기반으로 만드세요(`f"chk_{id}"`, `f"del_{id}"`). 인덱스 기반 key를 쓰면 삭제한 뒤 체크 상태가 다른 아이템으로 밀립니다.
- 상태 변경 함수는 `on_*` 콜백(`on_add_submit`, `on_edit_start` 등)이 위젯 값을 `session_state`에서 읽어 호출합니다. 콜백은 경고나 알림을 `add_error` / `edit_error` / `save_error` / `toast`에 넣어 두고, 화면 함수가 이를 표시합니다.
- 체크박스는 `value=`를 쓰지 않습니다. 렌더링 직전에 `st.session_state[f"chk_{id}"]`를 저장된 값으로 맞춰 둡니다. 체크 콜백은 상태를 뒤집지 말고 위젯 값을 그대로 저장하세요(`set_checked`).
- 수정 행은 `st.form`으로 감싸 Enter로 저장되게 합니다. 첫 번째 제출 버튼(저장)이 Enter에 반응하니 버튼 순서를 바꾸지 마세요.
- 아이템 이름은 `st.markdown(..., unsafe_allow_html=True)`로 그리므로, 사용자 입력은 반드시 `html.escape()`로 이스케이프하세요.
- 스타일은 `app.py`의 `CSS` 상수에 있습니다. 행은 `st.container(key=...)`로 감싸고, Streamlit이 붙여 주는 `st-key-<key>` 클래스로 선택합니다(`item_<id>`, `editrow_<id>`, `add_row`, `summary`). key 접두사를 바꾸면 CSS도 같이 바꿔야 합니다.
  - 이 CSS는 Streamlit이 좁은 화면(약 640px 미만)에서 `st.columns`를 세로로 쌓는 동작을 막습니다.
  - 각 행에서는 이름 칸만 늘어나고 나머지 칸은 내용 크기만큼만 차지합니다.
  - 400px 이하에서는 수량 칸과 버튼 여백을 줄입니다. 화면 폭 320px까지 확인했습니다.
- 테마는 `.streamlit/config.toml`의 `[theme.light]` / `[theme.dark]`에 둡니다. `[theme]`에 바로 색을 지정하면 다크 모드가 꺼지니 그렇게 하지 마세요.
- `client.showErrorDetails = "none"`이라 에러가 나도 화면에는 "에러가 났다"는 안내만 보입니다. 자세한 traceback은 서버를 띄운 터미널(로그)에서 확인하세요.
- 상태 변경은 `on_click` / `on_change` 콜백에서 하세요. 렌더 루프 안에서 리스트를 바로 수정하면 화면이 한 박자 늦게 반영되거나 순회 중 변경 버그가 생깁니다.
- Streamlit Community Cloud는 재시작할 때 로컬 파일이 초기화될 수 있습니다. JSON 저장은 로컬용이라는 점을 기억하세요.

## 배포

GitHub에 올린 뒤 Streamlit Community Cloud에서 `app.py`를 메인 파일로 배포합니다. 경로는 상대 경로를 쓰고, 비밀값은 `.streamlit/secrets.toml`(gitignore 대상)이나 Cloud의 Secrets에 둡니다.
