import email
import imaplib
import json
import re
import time as time_module
from email.header import decode_header
from pathlib import Path

import requests
import streamlit as st
from datetime import datetime, time as dtime
import pytz
from streamlit_autorefresh import st_autorefresh

JST = pytz.timezone("Asia/Tokyo")

st.set_page_config(page_title="なみ子ダッシュボード", page_icon="🦉", layout="centered")

# ── 簡易パスワードゲート ─────────────────────────────────────────
# リポジトリ自体はStreamlit Community Cloudの制約でPublicにする必要があるため、
# 個人情報を含む内容(今日のtodo等)を見るにはここで簡単な認証をかける。
_dashboard_password = st.secrets.get("DASHBOARD_PASSWORD")
if _dashboard_password:
    if not st.session_state.get("authed"):
        pw = st.text_input("パスワード", type="password")
        if pw == _dashboard_password:
            st.session_state["authed"] = True
            st.rerun()
        elif pw:
            st.error("パスワードが違います")
        if not st.session_state.get("authed"):
            st.stop()

# 1分ごとに自動更新（ライフフローチャートの現在地点を追従させるため）
st_autorefresh(interval=60 * 1000, key="dashboard_refresh")

st.markdown("""
<style>
@media (max-width: 640px) {
    h1 { font-size: 1.4rem !important; }
    .block-container { padding: 1rem 0.75rem !important; }
}
</style>
""", unsafe_allow_html=True)

st.title("🦉 なみ子ダッシュボード")
st.caption("よく見る情報を1画面に。まずは天気とライフフローチャートから。")

EBETSU_LAT, EBETSU_LON = 42.9, 141.6


# ── 天気セクション ──────────────────────────────────────────────
# Streamlit Community Cloudは複数アプリでIPを共有しており、Open-Meteo側の
# IP単位レート制限に他アプリの分も含めて引っかかることがある（自アプリの
# リクエスト頻度を下げてもこの共有IP問題は解決しない）。そのため、直近の
# 取得成功データをディスクに残し、リトライも尽きた時はそれを使い回す。
WEATHER_CACHE_FILE = Path("/tmp/namiko_dashboard_weather_cache.json")


@st.cache_data(ttl=1800)  # 30分キャッシュ（Open-Meteo APIを毎回叩かない）
def fetch_weather():
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": EBETSU_LAT,
        "longitude": EBETSU_LON,
        "current": "temperature_2m,weather_code",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "timezone": "Asia/Tokyo",
        "forecast_days": 2,
    }
    last_error = None
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, timeout=10)
            r.raise_for_status()
            data = r.json()
            data["_stale"] = False
            WEATHER_CACHE_FILE.write_text(json.dumps(data))
            return data
        except Exception as e:
            last_error = e
            if attempt < 2:
                time_module.sleep(2 * (attempt + 1))

    if WEATHER_CACHE_FILE.exists():
        data = json.loads(WEATHER_CACHE_FILE.read_text())
        data["_stale"] = True
        return data
    raise last_error


WEATHER_EMOJI = {
    0: "☀️", 1: "🌤️", 2: "⛅", 3: "☁️",
    45: "🌫️", 48: "🌫️",
    51: "🌦️", 53: "🌦️", 55: "🌦️",
    61: "🌧️", 63: "🌧️", 65: "🌧️",
    71: "🌨️", 73: "🌨️", 75: "🌨️",
    80: "🌦️", 81: "🌧️", 82: "🌧️",
    95: "⛈️", 96: "⛈️", 99: "⛈️",
}


def weather_icon(code: int) -> str:
    return WEATHER_EMOJI.get(code, "🌡️")


st.subheader("🌤️ 恵庭市の天気")
try:
    data = fetch_weather()
    cur = data["current"]
    daily = data["daily"]

    if data.get("_stale"):
        st.caption("⚠️ 最新データが取得できず、前回取得できた時点のものを表示しています")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("現在の気温", f"{cur['temperature_2m']:.0f}℃",
                   label_visibility="visible")
        st.markdown(f"<div style='font-size:2rem; text-align:center'>{weather_icon(cur['weather_code'])}</div>",
                    unsafe_allow_html=True)
    with col2:
        st.metric("今日 最高/最低", f"{daily['temperature_2m_max'][0]:.0f}℃ / {daily['temperature_2m_min'][0]:.0f}℃")
        st.markdown(f"<div style='text-align:center'>降水確率 {daily['precipitation_probability_max'][0]}%</div>",
                    unsafe_allow_html=True)
    with col3:
        st.metric("明日 最高/最低", f"{daily['temperature_2m_max'][1]:.0f}℃ / {daily['temperature_2m_min'][1]:.0f}℃")
        st.markdown(f"<div style='text-align:center'>降水確率 {daily['precipitation_probability_max'][1]}%</div>",
                    unsafe_allow_html=True)
except Exception as e:
    st.error(f"天気データの取得に失敗しました：{e}")

st.divider()

# ── ライフフローチャート セクション ──────────────────────────────
st.subheader("🗓️ ライフフローチャート 今どこ？")

TIME_BLOCKS = [
    (dtime(4, 0),  dtime(4, 30), "🌄", "デジタルデトックス", "スマホ/PC禁止。水1杯→カーテン開け→朝日→ストレッチ→瞑想"),
    (dtime(4, 30), dtime(5, 0),  "📱", "Duolingo・PC解禁", "英語ウォームアップ"),
    (dtime(5, 0),  dtime(5, 5),  "💻", "PC起動", "朝の起動リンク一覧を展開(Claude/ChatGPT/Substack/Discord)"),
    (dtime(5, 5),  dtime(5, 25), "📰", "漫画生成→配信", "原稿到着→漫画生成→なみ子コメント→Substack配信"),
    (dtime(5, 25), dtime(5, 55), "⏳", "余裕バッファ", "前倒し作業・見直し・SNS展開"),
    (dtime(5, 55), dtime(6, 0),  "🔄", "トランジション儀式①", "席を立つ・水を飲む"),
    (dtime(6, 0),  dtime(6, 55), "👥", "ZOOM朝活", "参加に集中・並行作業なし"),
    (dtime(7, 0),  dtime(8, 0),  "🚗", "お迎え→朝食→送り", "駅へお迎え→一緒に朝食→職場へ送る"),
    (dtime(8, 0),  dtime(17, 0), "💼", "見守りの仕事(本業)", ""),
    (dtime(17, 0), dtime(18, 0), "🚗", "お迎え→帰宅", ""),
    (dtime(18, 0), dtime(19, 30), "🎯", "ビジョン深掘り", "タイマー90分固定(火・金は深掘り、他は15分レビュー)"),
    (dtime(19, 30), dtime(21, 30), "🛀", "自由・回復の時間", ""),
    (dtime(21, 30), dtime(22, 0), "🌙", "シャットダウン儀式", "1日の振り返り日記・明日の漫画ネタ・Substack下書き"),
    (dtime(22, 0), dtime(23, 59, 59), "😴", "就寝", "6時間睡眠確保"),
]
# 0:00〜4:00 も就寝扱い
SLEEP_EARLY = (dtime(0, 0), dtime(4, 0), "😴", "就寝", "6時間睡眠確保")


def find_current_block(now_t: dtime):
    if now_t < dtime(4, 0):
        return SLEEP_EARLY
    for start, end, emoji, title, detail in TIME_BLOCKS:
        if start <= now_t < end:
            return (start, end, emoji, title, detail)
    return TIME_BLOCKS[-1]


now_jst = datetime.now(JST)
now_t = now_jst.time()
block = find_current_block(now_t)
start, end, emoji, title, detail = block

st.markdown(
    f"""<div style="background:#2b6cb022; border-left:6px solid #2b6cb0;
    padding:18px; border-radius:10px; margin:10px 0">
    <div style="font-size:0.85rem; color:#888">{now_jst.strftime('%H:%M')} 現在</div>
    <div style="font-size:1.6rem; font-weight:bold; margin-top:4px">{emoji} {title}</div>
    <div style="font-size:0.95rem; color:#555; margin-top:4px">{detail}</div>
    <div style="font-size:0.8rem; color:#999; margin-top:8px">
      {start.strftime('%H:%M')} 〜 {end.strftime('%H:%M') if end != dtime(23,59,59) else '4:00'}
    </div>
    </div>""",
    unsafe_allow_html=True,
)

with st.expander("1日の全体スケジュールを見る"):
    for start, end, emoji, title, detail in TIME_BLOCKS:
        is_now = start <= now_t < end
        bg = "#2b6cb022" if is_now else "transparent"
        st.markdown(
            f"""<div style="padding:8px 12px; border-radius:6px; margin:2px 0; background:{bg}">
            <b>{start.strftime('%H:%M')}</b> {emoji} {title}
            {' <span style="color:#2b6cb0">← 今ここ</span>' if is_now else ''}
            </div>""",
            unsafe_allow_html=True,
        )

st.divider()

# ── 今日のtodo セクション ──────────────────────────────────────
# 個人の予定を含むため、公開リポジトリには置かず非公開Gistから取得する。
# Gist IDはStreamlit Secretsに保存（リポジトリには一切書かない）。
st.subheader("✅ 今日のtodo")

GIST_ID = st.secrets.get("TODO_GIST_ID")
GIST_WRITE_TOKEN = st.secrets.get("GIST_WRITE_TOKEN")  # Gist専用スコープの弱い権限のトークン


def _gist_read_headers():
    # 認証なしのGitHub API GETは60回/時間/IPしか叩けない。Streamlit Community Cloudは
    # 他アプリとIPを共有しているため、この枠を他アプリの分も含めてすぐ使い切ってしまい
    # todo取得が失敗する(2026-08-13発覚。天気429と同根の「共有IPで無認証枠を食い合う」
    # 問題)。書き込み用に発行済みのGIST_WRITE_TOKENを読み取りにも流用すると、認証あり
    # 扱いになり上限が5000回/時間まで跳ね上がるため、これで根本的に解決する。
    if GIST_WRITE_TOKEN:
        return {"Authorization": f"Bearer {GIST_WRITE_TOKEN}"}
    return {}


@st.cache_data(ttl=300)  # 5分キャッシュ（Gist APIを毎回叩かない）
def fetch_todo_from_gist(gist_id: str) -> str | None:
    try:
        r = requests.get(f"https://api.github.com/gists/{gist_id}", headers=_gist_read_headers(), timeout=10)
        r.raise_for_status()
        return r.json()["files"]["today.md"]["content"]
    except Exception:
        return None


def fetch_todo_from_gist_fresh(gist_id: str) -> str | None:
    """書き込み前に使う、キャッシュを経由しない最新取得（他経路の更新と衝突しないため）"""
    try:
        r = requests.get(f"https://api.github.com/gists/{gist_id}", headers=_gist_read_headers(), timeout=10)
        r.raise_for_status()
        return r.json()["files"]["today.md"]["content"]
    except Exception:
        return None


def toggle_checklist_item(gist_id: str, write_token: str, target_index: int, new_checked: bool) -> bool:
    """チェックリストセクションのN番目(1始まり)の項目の完了状態を書き換えてGistへPATCHする。
    成功したらTrueを返す。ダッシュボードからの書き戻しなので、直前に最新内容を取り直してから
    書き換える(10分おきのローカル同期と衝突する時間差を極力小さくするため)。"""
    content = fetch_todo_from_gist_fresh(gist_id)
    if content is None:
        return False

    lines = content.splitlines()
    out_lines = []
    in_checklist = False
    count = 0
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            in_checklist = "今日のtodo(チェックリスト)" in stripped
            out_lines.append(line)
            continue
        if in_checklist:
            m = re.match(r"^(-\s*)\[( |x|X)\](\s*.*)$", stripped)
            if m:
                count += 1
                if count == target_index:
                    mark = "x" if new_checked else " "
                    line = f"{m.group(1)}[{mark}]{m.group(3)}"
        out_lines.append(line)

    new_content = "\n".join(out_lines) + "\n"

    try:
        r = requests.patch(
            f"https://api.github.com/gists/{gist_id}",
            headers={
                "Authorization": f"Bearer {write_token}",
                "Accept": "application/vnd.github+json",
            },
            json={"files": {"today.md": {"content": new_content}}},
            timeout=10,
        )
        r.raise_for_status()
    except Exception:
        return False

    fetch_todo_from_gist.clear()  # キャッシュを破棄して次回表示で最新を取る
    return True


def make_checklist_toggle_handler(index: int, new_value_key: str):
    def handler():
        new_checked = st.session_state[new_value_key]
        ok = toggle_checklist_item(GIST_ID, GIST_WRITE_TOKEN, index, new_checked)
        if not ok:
            st.session_state["_checklist_toggle_error"] = True
    return handler


SECTION_META = {
    "今日のtodo(チェックリスト)": ("📋", False),
    "今日やったこと": ("✅", True),   # (アイコン, 完了済みとして薄く見せる)
    "明日やること": ("📅", False),
    "今後やること": ("🗓", False),
}


def render_item(it: str, number: int | None = None):
    """`- [x] ...` / `- [ ] ...` はチェックボックス風に、それ以外は通常の箇条書きで表示。
    numberを渡すとチェックリスト項目に通し番号を付ける（会話で「1番から4番まで終了」と
    言えばなみ子がこの番号を頼りに該当行を特定できるようにするため）"""
    m = re.match(r"^\[( |x|X)\]\s*(.*)$", it)
    if not m:
        st.markdown(f"- {it}")
        return
    checked, label = m.group(1).lower() == "x", m.group(2)
    prefix = f"{number}. " if number is not None else ""
    if checked:
        st.markdown(f"- {prefix}✅ ~~{label}~~")
    else:
        st.markdown(f"- {prefix}⬜ {label}")


def parse_todo_md(text: str):
    """`## 見出し` ごとに区切って {見出し: [箇条書き, ...]} を返す"""
    sections = {}
    current = None
    for line in text.splitlines():
        m = re.match(r"^##\s*[^\w\s]*\s*(.+)$", line.strip())
        if m:
            current = m.group(1).strip()
            sections[current] = []
            continue
        item = re.match(r"^-\s+(.*)$", line.strip())
        if item and current:
            sections[current].append(item.group(1).strip())
    return sections


todo_text = fetch_todo_from_gist(GIST_ID) if GIST_ID else None

if todo_text:
    sections = parse_todo_md(todo_text)

    tab_labels = [f"{SECTION_META.get(name, ('📌', False))[0]} {name}" for name in sections]
    tabs = st.tabs(tab_labels) if sections else []

    for tab, (name, items) in zip(tabs, sections.items()):
        with tab:
            if not items:
                st.caption("（まだ空です）")
                continue
            is_checklist = (name == "今日のtodo(チェックリスト)")
            if is_checklist and GIST_WRITE_TOKEN:
                if st.session_state.get("_checklist_toggle_error"):
                    st.warning("チェックの保存に失敗しました。もう一度お試しください。")
                    st.session_state["_checklist_toggle_error"] = False
                for i, it in enumerate(items, start=1):
                    m = re.match(r"^\[( |x|X)\]\s*(.*)$", it)
                    if not m:
                        st.markdown(f"- {it}")
                        continue
                    checked, label = m.group(1).lower() == "x", m.group(2)
                    widget_key = f"chk_{i}_{hash(label) & 0xffff}"
                    st.checkbox(
                        f"{i}. {label}",
                        value=checked,
                        key=widget_key,
                        on_change=make_checklist_toggle_handler(i, widget_key),
                    )
            else:
                for i, it in enumerate(items, start=1):
                    render_item(it, number=i if is_checklist else None)
                if is_checklist and not GIST_WRITE_TOKEN:
                    st.caption("(画面からのチェックはまだ未設定です)")

    st.caption("PCから10分おきに自動同期されています")
elif GIST_ID:
    st.info("todoデータの取得に失敗しました。", icon="🚧")
else:
    st.info("todoデータがまだ設定されていません。", icon="🚧")

st.divider()

# ── メールヘッドライン セクション ────────────────────────────────
# yama@namiwodasu.comはロリポップ側でyasu.moco@gmail.comへ転送設定済みなので
# ([[reference_yama_email_webmail]])、Gmailに1本IMAP接続するだけで両アドレス分を
# 拾える。宛先ヘッダーを見てどちらの窓口宛だったかを判定して表示だけ分ける。
st.subheader("📧 メール")

GMAIL_ADDRESS = st.secrets.get("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = st.secrets.get("GMAIL_APP_PASSWORD")
YAMA_ADDRESS = "yama@namiwodasu.com"


def _decode_mime_header(raw: str) -> str:
    if not raw:
        return ""
    parts = decode_header(raw)
    out = ""
    for text, enc in parts:
        if isinstance(text, bytes):
            out += text.decode(enc or "utf-8", errors="replace")
        else:
            out += text
    return out


@st.cache_data(ttl=600)  # 10分キャッシュ（IMAPへの接続を毎回張らない）
def fetch_recent_emails(address: str, app_password: str, limit: int = 15):
    if not address or not app_password:
        return None
    try:
        imap = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        imap.login(address, app_password)
        imap.select("INBOX", readonly=True)
        status, data = imap.search(None, "ALL")
        if status != "OK":
            imap.logout()
            return None
        ids = data[0].split()[-limit:][::-1]  # 直近から新しい順
        results = []
        for eid in ids:
            status, msg_data = imap.fetch(
                eid, "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE TO DELIVERED-TO MESSAGE-ID)])"
            )
            if status != "OK" or not msg_data or not msg_data[0]:
                continue
            msg = email.message_from_bytes(msg_data[0][1])
            to_field = (msg.get("To", "") + " " + msg.get("Delivered-To", "")).lower()
            account = "yama@" if YAMA_ADDRESS in to_field else "yasu.moco@"
            message_id = (msg.get("Message-ID") or "").strip("<>")
            results.append({
                "subject": _decode_mime_header(msg.get("Subject", "")) or "(件名なし)",
                "sender": _decode_mime_header(msg.get("From", "")),
                "date": msg.get("Date", ""),
                "account": account,
                "message_id": message_id,
            })
        imap.logout()
        return results
    except Exception:
        return None


emails = fetch_recent_emails(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)

if emails is not None:
    if not emails:
        st.caption("新着メールはありません")
    for mail in emails:
        gmail_url = (
            f"https://mail.google.com/mail/u/0/#search/rfc822msgid%3A{mail['message_id']}"
            if mail["message_id"] else "https://mail.google.com/mail/u/0/"
        )
        badge = "🟣" if mail["account"] == "yama@" else "🔵"
        st.markdown(
            f"{badge} **[{mail['subject']}]({gmail_url})**  \n"
            f"<span style='color:#888; font-size:0.85rem'>{mail['sender']} ・ {mail['account']}</span>",
            unsafe_allow_html=True,
        )
    st.caption("🔵 yasu.moco@ 　🟣 yama@(転送分) 　クリックでGmailを開きます")
elif GMAIL_ADDRESS and GMAIL_APP_PASSWORD:
    st.info("メールの取得に失敗しました。", icon="🚧")
else:
    st.info("メール連携は未設定です。", icon="🚧")

st.markdown(
    """
    <div style="text-align:center; padding:12px 0 4px">
      <span style="font-size:0.8rem; color:#aaa; letter-spacing:0.05em">
        気象データ：<a href="https://open-meteo.com/" target="_blank" style="color:#aaa">Open-Meteo</a>
      </span><br>
      <span style="font-size:0.95rem; color:#888; font-weight:bold; letter-spacing:0.12em; margin-top:6px; display:inline-block">
        制作監督　波を出す
      </span>
    </div>
    """,
    unsafe_allow_html=True,
)
