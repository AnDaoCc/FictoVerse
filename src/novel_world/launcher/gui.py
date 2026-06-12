from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

from novel_world.launcher.api import LauncherApi
from novel_world.launcher.bootstrap import get_root

WINDOW_BG = "#faf8f5"
ICON_REL = Path("packaging") / "assets" / "launcher-icon.ico"


def resolve_icon_path() -> Path | None:
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            path = Path(meipass) / ICON_REL
            return path if path.is_file() else None
        return None
    path = get_root() / ICON_REL
    return path if path.is_file() else None


def resolve_ui_dir() -> Path:
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass) / "novel_world" / "launcher" / "ui"
    return Path(__file__).resolve().parent / "ui"


def main() -> None:
    if sys.platform != "win32":
        print("GUI 启动器目前仅支持 Windows。")
        sys.exit(1)

    try:
        import webview
    except ImportError:
        msg = "缺少 pywebview，请运行：pip install -e \".[launcher]\""
        if sys.platform == "win32":
            try:
                import ctypes

                ctypes.windll.user32.MessageBoxW(0, msg, "FictoVerse 启动器", 0x10)
            except Exception:
                print(msg)
        else:
            print(msg)
        sys.exit(1)

    api = LauncherApi()
    ui_dir = resolve_ui_dir()
    index_html = ui_dir / "index.html"
    if not index_html.exists():
        print(f"未找到界面文件：{index_html}")
        sys.exit(1)

    window = webview.create_window(
        "FictoVerse",
        url=str(index_html),
        width=1200,
        height=800,
        resizable=True,
        min_size=(1000, 700),
        js_api=api,
        background_color=WINDOW_BG,
    )

    def poll_status() -> None:
        while True:
            time.sleep(2)
            if not webview.windows:
                break
            try:
                status = api.get_status()
                payload = json.dumps(status, ensure_ascii=False)
                window.evaluate_js(
                    f"window.__applyStatus && window.__applyStatus({payload})"
                )
                logs = api.get_logs()
                if logs:
                    logs_payload = json.dumps(logs, ensure_ascii=False)
                    window.evaluate_js(
                        f"window.__applyLogs && window.__applyLogs({logs_payload})"
                    )
                task = api.get_task_status()
                if task and task.get("running"):
                    task_payload = json.dumps(task, ensure_ascii=False)
                    window.evaluate_js(
                        f"window.__applyTaskProgress && window.__applyTaskProgress({task_payload})"
                    )
            except Exception:
                pass

    threading.Thread(target=poll_status, daemon=True).start()
    start_kwargs: dict = {"gui": "edgechromium", "http_server": True}
    icon_path = resolve_icon_path()
    if icon_path is not None:
        start_kwargs["icon"] = str(icon_path)
    webview.start(**start_kwargs)


if __name__ == "__main__":
    main()
