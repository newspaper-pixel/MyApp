"""가벼운 쇼핑 리스트 앱 (Streamlit).

요구사항은 PRD.md 참고. 4단계 검토에서 나온 버그 수정 반영.
"""

import html
import json
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

import streamlit as st

DATA_FILE = Path(__file__).parent / "data" / "items.json"

MIN_QTY, MAX_QTY = 1, 999
EMPTY_NAME_MSG = "아이템 이름을 입력해 주세요."
QTY_MSG = f"수량은 {MIN_QTY}~{MAX_QTY} 사이의 정수로 입력해 주세요."
SAVE_FAILED_MSG = "저장에 실패했어요. 잠시 후 다시 시도해 주세요. (변경 내용은 반영되지 않았어요)"
GONE_MSG = "다른 화면에서 이미 삭제된 아이템이에요."

# 추가 버튼을 연달아 누르면 빈 이름 경고가 잘못 뜨거나 같은 아이템이 두 번 추가될 수 있다.
# 직전 추가 후 이 시간(초) 안에 들어온 빈 제출과 같은 이름 제출은 조용히 무시한다.
DOUBLE_SUBMIT_WINDOW = 1.5

# 같은 서버 프로세스의 여러 세션(탭)이 동시에 읽고-수정하고-쓰는 것을 막는다.
_STORE_LOCK = threading.Lock()

# 행 컨테이너는 key로 구분한다. Streamlit은 key="item_<id>"인 컨테이너에
# "st-key-item_<id>" 클래스를 붙이므로 CSS에서 접두사로 선택할 수 있다.
CSS = """
<style>
/* 제목: 한글 단어 중간에서 줄바꿈되지 않게, 아주 좁은 화면에서는 조금 작게 */
h1 { word-break: keep-all; }
@media (max-width: 360px) { h1 { font-size: 2rem !important; } }

/* 요약: 모바일에서도 지표 3개를 한 줄로 */
.st-key-summary [data-testid="stHorizontalBlock"] { flex-wrap: nowrap; gap: 0.5rem; }
.st-key-summary [data-testid="stColumn"] { min-width: 0 !important; }
.st-key-summary [data-testid="stMetric"] {
  background: rgba(128, 128, 128, 0.08);
  border-radius: 0.75rem;
  padding: 0.5rem 0.75rem;
}
.st-key-summary [data-testid="stMetricValue"] { font-size: 1.5rem; }

/* 추가 폼과 아이템 행: 모바일에서 세로로 쌓이지 않게 */
.st-key-add_row [data-testid="stHorizontalBlock"],
[class*="st-key-item_"] [data-testid="stHorizontalBlock"],
[class*="st-key-editrow_"] [data-testid="stHorizontalBlock"] {
  flex-wrap: nowrap;
  gap: 0.5rem;
}
.st-key-add_row [data-testid="stColumn"],
[class*="st-key-item_"] [data-testid="stColumn"],
[class*="st-key-editrow_"] [data-testid="stColumn"] {
  min-width: 0 !important;
}
/* 이름 칸만 남는 폭을 모두 차지하고, 체크박스 / 수량 / 버튼 칸은 내용 크기만큼 */
.st-key-add_row [data-testid="stColumn"]:first-child,
[class*="st-key-item_"] [data-testid="stColumn"]:nth-child(2),
[class*="st-key-editrow_"] [data-testid="stColumn"]:first-child {
  flex: 1 1 0 !important;
  width: auto !important;
}
.st-key-add_row [data-testid="stColumn"]:not(:first-child),
[class*="st-key-item_"] [data-testid="stColumn"]:not(:nth-child(2)),
[class*="st-key-editrow_"] [data-testid="stColumn"]:not(:first-child) {
  flex: 0 0 auto !important;
  width: auto !important;
}
.st-key-add_row [data-testid="stColumn"]:nth-child(2) { width: 6rem !important; }
[class*="st-key-editrow_"] [data-testid="stColumn"]:nth-child(2) { width: 4.5rem !important; }
/* 아주 좁은 화면: 수량 칸과 버튼 여백을 줄여 이름 칸 폭을 확보 */
@media (max-width: 400px) {
  .st-key-add_row [data-testid="stColumn"]:nth-child(2) { width: 4.5rem !important; }
  [class*="st-key-editrow_"] [data-testid="stColumn"]:nth-child(2) { width: 3.5rem !important; }
  [class*="st-key-editrow_"] [data-testid="stHorizontalBlock"] { gap: 0.35rem; }
  [class*="st-key-editrow_"] button { padding: 0 0.4rem; }
  [class*="st-key-editrow_"] { padding: 0.5rem; }
}

/* 아이템 행 카드 */
[class*="st-key-item_"], [class*="st-key-editrow_"] {
  border: 1px solid rgba(128, 128, 128, 0.25);
  border-radius: 0.75rem;
  padding: 0.5rem 0.75rem;
}
[class*="st-key-editrow_"] {
  background: rgba(46, 158, 107, 0.10);
  border-color: rgba(46, 158, 107, 0.6);
}
[class*="st-key-item_"] button, [class*="st-key-editrow_"] button,
.st-key-add_row button {
  min-height: 2.5rem;
  min-width: 2.5rem;
  padding: 0 0.6rem;
}
[class*="st-key-item_"] [data-testid="stCheckbox"] { min-height: 2.5rem; align-items: center; }

/* 아이템 이름과 수량 배지 (마크다운 래퍼의 음수 여백 때문에 체크박스보다 아래로 처지지 않게) */
div:has(> .item-name) { margin-bottom: 0 !important; }
.item-name { overflow-wrap: anywhere; line-height: 1.4; }
.item-name.done { text-decoration: line-through; opacity: 0.5; }
.qty-badge {
  display: inline-block;
  margin-left: 0.4rem;
  padding: 0.05rem 0.5rem;
  border-radius: 999px;
  font-size: 0.8rem;
  background: rgba(46, 158, 107, 0.15);
  color: #2E9E6B;
  white-space: nowrap;
}
.done .qty-badge { background: rgba(128, 128, 128, 0.15); color: inherit; }
</style>
"""


# ---------------------------------------------------------------------------
# 상태 / 저장소
# ---------------------------------------------------------------------------

class SaveError(Exception):
    """저장소에 쓰지 못했을 때 발생한다."""


def init_state():
    """매 실행마다 저장소에서 최신 리스트를 읽어 session_state를 갱신한다.

    다른 탭이나 기기에서 바뀐 내용도 다음 상호작용 때 바로 보이게 하기 위해
    세션 시작 때 한 번만 읽지 않고 매번 다시 읽는다.
    """
    st.session_state["items"] = load_items()
    ids = {i["id"] for i in st.session_state["items"]}
    if st.session_state.get("editing_id") not in ids:
        st.session_state["editing_id"] = None


def load_items():
    """저장소에서 아이템 리스트를 읽어 반환한다.

    저장소를 바꿔도 UI 코드는 그대로 두도록 I/O는 이 함수와 save_items()에서만 한다.
    파일이 없으면 빈 리스트. 파일이 깨졌으면 다음 저장 때 덮어쓰지 않도록 따로 보관한 뒤
    빈 리스트를 반환한다. 형식이 잘못된 아이템은 고치거나 건너뛴다.
    """
    try:
        text = DATA_FILE.read_text(encoding="utf-8")
    except OSError:
        return []
    try:
        data = json.loads(text)
        if not isinstance(data, list):
            raise ValueError("items.json must contain a list")
    except ValueError:
        backup_broken_file()
        return []

    items, seen = [], set()
    for raw in data:
        item = normalize_item(raw)
        if item is not None and item["id"] not in seen:  # id가 중복되면 위젯 key가 겹친다
            seen.add(item["id"])
            items.append(item)
    return items


def normalize_item(raw):
    """저장된 dict 하나를 PRD 5장 데이터 모델로 맞춘다. 복구할 수 없으면 None."""
    if not isinstance(raw, dict):
        return None
    item_id, name = raw.get("id"), raw.get("name")
    if not isinstance(item_id, (str, int)) or isinstance(item_id, bool) or item_id == "":
        return None
    if not isinstance(name, str) or not name.strip():
        return None
    try:
        quantity = int(raw.get("quantity", MIN_QTY))
    except (TypeError, ValueError):
        quantity = MIN_QTY
    checked = raw.get("checked", False)
    if isinstance(checked, str):
        checked = checked.strip().lower() == "true"
    return {
        "id": str(item_id),
        "name": name.strip(),
        "quantity": min(max(quantity, MIN_QTY), MAX_QTY),
        "checked": checked is True,
        "created_at": str(raw.get("created_at", "")),
    }


def backup_broken_file():
    """읽을 수 없는 저장 파일을 items.broken-<시각>.json으로 옮겨 보관한다."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    try:
        DATA_FILE.replace(DATA_FILE.with_name(f"items.broken-{stamp}.json"))
    except OSError:
        pass


def save_items(items):
    """아이템 리스트를 저장소에 기록한다 (폴더가 없으면 생성). 실패하면 SaveError."""
    tmp = DATA_FILE.with_suffix(".tmp")
    try:
        DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(DATA_FILE)
    except OSError as e:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise SaveError(str(e)) from e


def commit(change):
    """저장소의 최신 리스트에 change(items)를 적용하고 저장한다.

    session_state에 들고 있던 리스트가 아니라 저장소를 다시 읽어 수정하므로
    여러 탭 / 기기에서 동시에 써도 서로의 변경을 덮어쓰지 않는다.
    change가 False를 반환하면 저장하지 않는다. 저장에 실패하면 화면 상태도 바꾸지 않는다.
    성공하면 True를 반환한다.
    """
    with _STORE_LOCK:
        items = load_items()
        if change(items) is False:
            st.session_state["items"] = items
            return False
        try:
            save_items(items)
        except SaveError:
            st.session_state["save_error"] = SAVE_FAILED_MSG
            return False
    st.session_state["items"] = items
    return True


def find_item(item_id, items=None):
    """id로 아이템을 찾는다. 없으면 None."""
    items = st.session_state["items"] if items is None else items
    return next((i for i in items if i["id"] == item_id), None)


# ---------------------------------------------------------------------------
# 상태 변경 (위젯 콜백에서 호출)
# ---------------------------------------------------------------------------

def new_item(name, quantity=1):
    """PRD 5장 데이터 모델에 맞는 아이템 dict를 만든다."""
    return {
        "id": str(uuid.uuid4()),
        "name": name,
        "quantity": quantity,
        "checked": False,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }


def validate(name, quantity):
    """입력값을 검사해 문제가 있으면 안내 문구를, 없으면 None을 반환한다."""
    if not name.strip():
        return EMPTY_NAME_MSG
    if quantity is None or quantity != int(quantity) or not MIN_QTY <= quantity <= MAX_QTY:
        return QTY_MSG
    return None


def add_item(name, quantity=1):
    """새 아이템을 리스트 맨 아래에 추가한다. (FR-1)

    입력값이 잘못됐거나 저장에 실패하면 False를 반환한다.
    """
    if validate(name, quantity):
        return False
    item = new_item(name.strip(), int(quantity))
    return commit(lambda items: items.append(item))


def update_item(item_id, name, quantity):
    """아이템의 이름과 수량을 수정한다. (FR-2)

    입력값이 잘못됐거나, 아이템이 이미 없거나, 저장에 실패하면 False를 반환한다.
    """
    if validate(name, quantity):
        return False

    def change(items):
        item = find_item(item_id, items)
        if item is None:
            return False
        item["name"] = name.strip()
        item["quantity"] = int(quantity)

    return commit(change)


def delete_item(item_id):
    """아이템을 삭제한다. (FR-3) 삭제한 아이템을 반환하고, 없었으면 None."""
    deleted = []

    def change(items):
        deleted.extend(i for i in items if i["id"] == item_id)
        items[:] = [i for i in items if i["id"] != item_id]

    if not commit(change) or not deleted:
        return None
    if st.session_state["editing_id"] == item_id:
        st.session_state["editing_id"] = None
    return deleted[0]


def set_checked(item_id, checked):
    """아이템의 체크 상태를 지정한다. (FR-4)

    상태를 뒤집지 않고 값을 지정하므로, 다른 탭에서 먼저 바뀌었어도
    사용자가 화면에서 본 체크박스 상태와 저장 결과가 어긋나지 않는다.
    """
    def change(items):
        item = find_item(item_id, items)
        if item is None:
            return False
        item["checked"] = bool(checked)

    return commit(change)


def clear_checked():
    """체크된 아이템을 모두 삭제한다. (FR-3) 삭제한 개수를 반환한다."""
    removed = []

    def change(items):
        removed.extend(i["id"] for i in items if i["checked"])
        items[:] = [i for i in items if not i["checked"]]

    if not commit(change):
        return 0
    if st.session_state["editing_id"] in removed:
        st.session_state["editing_id"] = None
    return len(removed)


# 아래 on_* 함수는 위젯 콜백이다. 콜백은 렌더링 전에 실행되므로
# 클릭 결과가 같은 실행(rerun)에서 바로 화면에 반영된다.

def on_add_submit():
    name = st.session_state["add_name"].strip()
    qty = st.session_state["add_qty"]
    error = validate(name, qty)
    recent = time.time() - st.session_state.get("last_add_at", 0) < DOUBLE_SUBMIT_WINDOW
    # 연타하면 두 번째 제출에는 비워진 값이나 방금 추가한 이름이 그대로 실려 온다.
    if recent and (error == EMPTY_NAME_MSG or name == st.session_state.get("last_add_name")):
        return
    if error:
        st.session_state["add_error"] = error  # 입력값은 그대로 두어 고쳐서 다시 제출할 수 있게 한다
    elif add_item(name, qty):
        st.session_state["add_name"] = ""
        st.session_state["add_qty"] = 1
        st.session_state["last_add_at"] = time.time()
        st.session_state["last_add_name"] = name
        st.session_state["toast"] = f"🛒 '{name}'을(를) 추가했어요"


def on_toggle(item_id):
    if not set_checked(item_id, st.session_state[f"chk_{item_id}"]) and "save_error" not in st.session_state:
        st.session_state["toast"] = GONE_MSG


def on_delete(item_id):
    item = delete_item(item_id)
    if item is not None:
        st.session_state["toast"] = f"🗑️ '{item['name']}'을(를) 삭제했어요"
    elif "save_error" not in st.session_state:
        st.session_state["toast"] = GONE_MSG


def on_clear_checked():
    count = clear_checked()
    if count:
        st.session_state["toast"] = f"🧹 체크된 항목 {count}개를 삭제했어요"


def on_edit_start(item_id):
    item = find_item(item_id)
    if item is None:
        return
    st.session_state["editing_id"] = item_id
    st.session_state[f"edit_name_{item_id}"] = item["name"]
    st.session_state[f"edit_qty_{item_id}"] = item["quantity"]
    st.session_state.pop("edit_error", None)


def on_edit_save(item_id):
    name = st.session_state[f"edit_name_{item_id}"]
    qty = st.session_state[f"edit_qty_{item_id}"]
    error = validate(name, qty)
    if error:
        st.session_state["edit_error"] = error
        return
    if update_item(item_id, name, qty):
        st.session_state["editing_id"] = None
        st.session_state.pop("edit_error", None)
    elif "save_error" not in st.session_state:
        st.session_state["editing_id"] = None
        st.session_state["toast"] = GONE_MSG


def on_edit_cancel():
    st.session_state["editing_id"] = None
    st.session_state.pop("edit_error", None)


# ---------------------------------------------------------------------------
# 렌더링
# ---------------------------------------------------------------------------

def render_summary():
    """전체 / 완료 / 남은 개수와 진행률을 표시한다. (FR-5)"""
    items = st.session_state["items"]
    total = len(items)
    done = sum(1 for i in items if i["checked"])
    with st.container(key="summary"):
        col_total, col_done, col_left = st.columns(3)
        col_total.metric("전체", f"{total}개")
        col_done.metric("완료", f"{done}개")
        col_left.metric("남은", f"{total - done}개")
    ratio = done / total if total else 0.0
    st.progress(ratio, text=f"진행률 {ratio:.0%}")


def render_add_form():
    """아이템 추가 폼을 표시한다. (FR-1)"""
    # 수량에 min/max를 주면 범위 밖 입력을 Streamlit이 영어 툴팁으로만 막고
    # 제출이 조용히 무시되므로, 범위 검사는 validate()에서 직접 한다.
    # clear_on_submit을 쓰면 잘못 입력했을 때도 이름이 지워지므로, 성공했을 때만 콜백에서 비운다.
    # 콜백에서 위젯 값을 바꾸므로 기본값은 value= 대신 session_state로 준다 (둘 다 주면 경고가 뜬다).
    st.session_state.setdefault("add_qty", 1)
    with st.form("add_form", border=False):
        with st.container(key="add_row"):
            col_name, col_qty, col_btn = st.columns([6, 2, 1.5], vertical_alignment="bottom")
            col_name.text_input("아이템 이름", key="add_name", placeholder="예: 우유")
            col_qty.number_input("수량", key="add_qty", step=1)
            col_btn.form_submit_button("추가", type="primary", on_click=on_add_submit)
    if "add_error" in st.session_state:
        st.warning(st.session_state.pop("add_error"))


def render_item(item):
    """아이템 한 줄을 표시한다. 편집 중이면 편집 입력창을 보여준다."""
    item_id = item["id"]

    if st.session_state["editing_id"] == item_id:
        # 폼으로 감싸 이름 칸에서 Enter를 누르면 저장되게 한다 (첫 번째 제출 버튼이 실행됨).
        with st.container(key=f"editrow_{item_id}"):
            with st.form(f"edit_form_{item_id}", border=False):
                col_name, col_qty, col_save, col_cancel = st.columns(
                    [6, 2, 1, 1], vertical_alignment="bottom"
                )
                col_name.text_input("이름", key=f"edit_name_{item_id}")
                col_qty.number_input("수량", key=f"edit_qty_{item_id}", step=1)
                col_save.form_submit_button(
                    "저장", type="primary", on_click=on_edit_save, args=(item_id,)
                )
                col_cancel.form_submit_button("취소", on_click=on_edit_cancel)
            if "edit_error" in st.session_state:
                st.warning(st.session_state["edit_error"])
        return

    with st.container(key=f"item_{item_id}"):
        col_chk, col_name, col_edit, col_del = st.columns([1, 8, 1, 1], vertical_alignment="center")
        # 저장소 값으로 위젯 상태를 맞춘다. 다른 탭에서 바뀐 체크 상태도 그대로 보이게 하기 위함.
        st.session_state[f"chk_{item_id}"] = item["checked"]
        col_chk.checkbox(
            "구매 완료",
            key=f"chk_{item_id}",
            on_change=on_toggle,
            args=(item_id,),
            label_visibility="collapsed",
        )
        done = " done" if item["checked"] else ""
        col_name.markdown(
            f'<div class="item-name{done}">{html.escape(item["name"])}'
            f'<span class="qty-badge">x{item["quantity"]}</span></div>',
            unsafe_allow_html=True,
        )
        col_edit.button("✏️", key=f"edit_{item_id}", help="수정", on_click=on_edit_start, args=(item_id,))
        col_del.button("🗑️", key=f"del_{item_id}", help="삭제", on_click=on_delete, args=(item_id,))


def render_item_list():
    """아이템 리스트와 체크 / 수정 / 삭제 컨트롤을 표시한다. (FR-2~4, FR-6)"""
    items = st.session_state["items"]
    if not items:
        st.info("리스트가 비어 있어요. 살 물건을 추가해 보세요!", icon="🧺")
        return

    # 남은 아이템이 위, 체크된 아이템이 아래 (같은 그룹 안에서는 추가한 순서 유지)
    for item in sorted(items, key=lambda i: i["checked"]):
        render_item(item)

    st.button(
        "체크된 항목 모두 삭제",
        icon="🧹",
        on_click=on_clear_checked,
        disabled=not any(i["checked"] for i in items),
    )


def main():
    st.set_page_config(page_title="쇼핑 리스트", page_icon="🛒", layout="centered")
    init_state()
    st.markdown(CSS, unsafe_allow_html=True)

    if "toast" in st.session_state:
        st.toast(st.session_state.pop("toast"))

    st.title("🛒 쇼핑 리스트")
    if "save_error" in st.session_state:
        st.error(st.session_state.pop("save_error"), icon="⚠️")
    render_summary()
    st.divider()
    render_add_form()
    st.divider()
    render_item_list()


if __name__ == "__main__":
    main()
