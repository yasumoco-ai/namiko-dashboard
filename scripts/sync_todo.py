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
"""
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
TODO_DIR = Path.home() / "todo"
REPO_DIR = Path(__file__).resolve().parent.parent
GIST_ID_FILE = REPO_DIR / ".gist_id"
GH_TOKEN_FILE = TODO_DIR / ".gh_token"


def main():
    if not GIST_ID_FILE.exists():
        print(f"[sync_todo] {GIST_ID_FILE} が見つかりません。"
              f"先に `gh gist create` でgistを作成しIDを保存してください", file=sys.stderr)
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

    result = subprocess.run(
        ["gh", "gist", "edit", gist_id, "--filename", "today.md", str(src)],
        capture_output=True, text=True, env=env,
    )
    if result.returncode != 0:
        print(f"[sync_todo] gist更新に失敗: {result.stderr}", file=sys.stderr)
        sys.exit(1)

    print(f"[sync_todo] {today} 分をGistへ同期しました")


if __name__ == "__main__":
    main()
