#!/usr/bin/env python3
"""
~/todo/YYYY-MM-DD.md（今日の分）を、非公開のGitHub Gistへ同期する。

namiko-dashboardのリポジトリはStreamlit Community Cloud（無料版）の制約上
公開(Public)にする必要があるため、個人の予定が入るtodoの中身はリポジトリに
コミットせず、このスクリプトが直接Gist(secret)へpushする。
app.py側はこのGistをGist IDだけを頼りに読みに行く（IDはStreamlit Secretsに
保存し、公開リポジトリには一切書かない）。

事前準備: `gh gist create` で1回だけsecret gistを作成し、
そのgist IDを ~/Projects/namiko-dashboard/.gist_id に保存しておくこと
（.gist_idは.gitignore対象、リポジトリには含まれない）。

cronからの実行時の注意: `gh` CLIの認証はmacOSキーチェーンに保存されているが、
cronはログインセッション外で動くためキーチェーンにアクセスできず401エラーに
なる（2026-08-11に実際発生・原因特定）。そのため ~/todo/.gh_token に
`gh auth token` の出力を保存しておき、このスクリプトが `GH_TOKEN` 環境変数として
渡すことで回避する（.gh_tokenはgit管理下に置かない。パーミッション600推奨）。

ダッシュボード側からのチェックボックス書き戻しとの競合について:
namiko-dashboard側もこのGistに直接書き込めるようになったため（2026-08-11）、
このスクリプトが単純に「ローカルの内容で無条件上書き」すると、ダッシュボード側で
付けたチェックが10分以内に消えてしまう恐れがある。そのため、push前に必ず
現在のGistの内容を取得し、チェックリスト内で「Gist側はチェック済みだが
ローカル側は未チェック」の項目があればローカル側にも先に反映してから
pushする（テキスト一致でマッチング）。
"""
import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
TODO_DIR = Path.home() / "todo"
REPO_DIR = Path(__file__).resolve().parent.parent
GIST_ID_FILE = REPO_DIR / ".gist_id"
GH_TOKEN_FILE = TODO_DIR / ".gh_token"
FAIL_COUNT_FILE = TODO_DIR / ".sync_todo_fail_count"
DISCORD_TOKEN_FILE = TODO_DIR / ".discord_token"

# 連続でこの回数失敗したらDiscordに一報する（10分間隔なら約1時間分）
FAIL_ALERT_THRESHOLD = 6

DISCORD_CHANNEL = "1507595262301048894"


def notify_discord(message):
    # このリポジトリはStreamlit Cloud用にPublicにしているため、
    # BotトークンはGitHub Push Protectionにも指摘される通りハードコード禁止。
    # ~/todo/.discord_token（git管理外）から読み込む。
    if not DISCORD_TOKEN_FILE.exists():
        return
    token = DISCORD_TOKEN_FILE.read_text(encoding="utf-8").strip()
    data = json.dumps({"content": message}).encode("utf-8")
    req = urllib.request.Request(
        f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL}/messages",
        data=data,
        headers={
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json",
            "User-Agent": "DiscordBot (https://discord.com, 10)",
        },
    )
    try:
        urllib.request.urlopen(req)
    except Exception:
        pass  # 通知自体の失敗でスクリプトを落とさない


def read_fail_count():
    try:
        return int(FAIL_COUNT_FILE.read_text().strip())
    except (FileNotFoundError, ValueError):
        return 0


def record_failure(error_detail):
    count = read_fail_count() + 1
    FAIL_COUNT_FILE.write_text(str(count))
    if count == FAIL_ALERT_THRESHOLD:
        notify_discord(
            f"⚠️ todo同期(sync_todo.py)が{count}回連続で失敗しています。\n"
            f"直近のエラー: {error_detail[:300]}\n"
            f"ダッシュボードのtodoが古いままの可能性があります。"
        )


def record_success():
    if FAIL_COUNT_FILE.exists():
        FAIL_COUNT_FILE.unlink()


def fetch_gist_content(gist_id, env):
    result = subprocess.run(
        ["gh", "api", f"gists/{gist_id}"],
        capture_output=True, text=True, env=env,
    )
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)["files"]["today.md"]["content"]
    except (KeyError, json.JSONDecodeError):
        return None


def checked_labels_in_checklist(text):
    """テキストのチェックリストセクションから、チェック済み項目のラベル文字列集合を返す"""
    labels = set()
    in_checklist = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            in_checklist = "今日のtodo(チェックリスト)" in stripped
            continue
        if in_checklist:
            m = re.match(r"^-\s*\[( |x|X)\]\s*(.*)$", stripped)
            if m and m.group(1).lower() == "x":
                labels.add(m.group(2).strip())
    return labels


def merge_gist_checks_into_local(local_text, gist_checked_labels):
    """Gist側で既にチェック済みの項目を、ローカルのテキストにも反映する。
    (更新後テキスト, 変更があったかどうか) のタプルを返す"""
    if not gist_checked_labels:
        return local_text, False
    out_lines = []
    in_checklist = False
    changed = False
    for line in local_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            in_checklist = "今日のtodo(チェックリスト)" in stripped
            out_lines.append(line)
            continue
        if in_checklist:
            m = re.match(r"^(\s*-\s*)\[( )\](\s*)(.*)$", line)
            if m and m.group(4).strip() in gist_checked_labels:
                line = f"{m.group(1)}[x]{m.group(3)}{m.group(4)}"
                changed = True
        out_lines.append(line)
    return "\n".join(out_lines) + ("\n" if local_text.endswith("\n") else ""), changed


def main():
    if not GIST_ID_FILE.exists():
        print(f"[sync_todo] {GIST_ID_FILE} が見つかりません。"
              f"先に `gh gist create` でgistを作成しIDを保存してください", file=sys.stderr)
        record_failure(f"{GIST_ID_FILE} が見つかりません")
        sys.exit(1)

    gist_id = GIST_ID_FILE.read_text(encoding="utf-8").strip()

    today = datetime.now(JST).strftime("%Y-%m-%d")
    src = TODO_DIR / f"{today}.md"

    if not src.exists():
        print(f"[sync_todo] {src} が見つかりません、スキップ")
        return

    env = os.environ.copy()
    if GH_TOKEN_FILE.exists():
        env["GH_TOKEN"] = GH_TOKEN_FILE.read_text(encoding="utf-8").strip()

    # ダッシュボード側で先にチェックされた項目があれば、ローカルにも反映してから push する
    gist_content = fetch_gist_content(gist_id, env)
    if gist_content is not None:
        local_text = src.read_text(encoding="utf-8")
        gist_checked = checked_labels_in_checklist(gist_content)
        merged_text, changed = merge_gist_checks_into_local(local_text, gist_checked)
        if changed:
            src.write_text(merged_text, encoding="utf-8")
            print("[sync_todo] ダッシュボード側のチェックをローカルに反映しました")

    result = subprocess.run(
        ["gh", "gist", "edit", gist_id, "--filename", "today.md", str(src)],
        capture_output=True, text=True, env=env,
    )
    if result.returncode != 0:
        print(f"[sync_todo] gist更新に失敗: {result.stderr}", file=sys.stderr)
        record_failure(result.stderr)
        sys.exit(1)

    record_success()
    print(f"[sync_todo] {today} 分をGistへ同期しました")


if __name__ == "__main__":
    main()
