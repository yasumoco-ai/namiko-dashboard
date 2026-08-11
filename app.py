import re

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
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    return r.json()


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


@st.cache_data(ttl=300)  # 5分キャッシュ（Gist APIを毎回叩かない）
def fetch_todo_from_gist(gist_id: str) -> str | None:
    try:
        r = requests.get(f"https://api.github.com/gists/{gist_id}", timeout=10)
        r.raise_for_status()
        return r.json()["files"]["today.md"]["content"]
    except Exception:
        return None


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
            for i, it in enumerate(items, start=1):
                render_item(it, number=i if is_checklist else None)

    st.caption("PCから10分おきに自動同期されています")
elif GIST_ID:
    st.info("todoデータの取得に失敗しました。", icon="🚧")
else:
    st.info("todoデータがまだ設定されていません。", icon="🚧")

st.divider()
st.info("メール・チャット・Etsy/Substack状況などは次のバージョンで追加予定です。", icon="🚧")

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
