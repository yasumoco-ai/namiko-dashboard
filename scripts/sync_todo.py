#!/usr/bin/env python3
"""
~/todo/YYYY-MM-DD.md（今日の分）を namiko-dashboard/data/today.md にコピーし、
変更があればgit commit & pushする。

Streamlit Cloud はクラウド上で動くためローカルの ~/todo/ を直接読めない。
このスクリプトが「ローカル→GitHub」の橋渡しをすることで、
app.py はリポジトリ内の data/today.md を読むだけで最新のtodoを表示できる。
"""
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
TODO_DIR = Path.home() / "todo"
REPO_DIR = Path(__file__).resolve().parent.parent
DEST = REPO_DIR / "data" / "today.md"


def main():
    today = datetime.now(JST).strftime("%Y-%m-%d")
    src = TODO_DIR / f"{today}.md"

    if not src.exists():
        print(f"[sync_todo] {src} が見つかりません、スキップ")
        return

    DEST.parent.mkdir(parents=True, exist_ok=True)
    new_content = src.read_text(encoding="utf-8")

    if DEST.exists() and DEST.read_text(encoding="utf-8") == new_content:
        print("[sync_todo] 変更なし、スキップ")
        return

    DEST.write_text(new_content, encoding="utf-8")

    subprocess.run(["git", "-C", str(REPO_DIR), "add", "data/today.md"], check=True)
    result = subprocess.run(
        ["git", "-C", str(REPO_DIR), "diff", "--cached", "--quiet"]
    )
    if result.returncode == 0:
        print("[sync_todo] ステージ後も差分なし、スキップ")
        return

    subprocess.run(
        ["git", "-C", str(REPO_DIR), "commit", "-m", f"sync todo {today}"],
        check=True,
    )
    subprocess.run(["git", "-C", str(REPO_DIR), "push"], check=True)
    print(f"[sync_todo] {today} 分を同期・pushしました")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        print(f"[sync_todo] エラー: {e}", file=sys.stderr)
        sys.exit(1)
