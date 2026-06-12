from __future__ import annotations

import sys
from pathlib import Path


def _prepend_src_to_path() -> None:
    if getattr(sys, "frozen", False):
        return
    root = Path(__file__).resolve().parents[3]
    src = root / "src"
    if src.is_dir():
        src_str = str(src)
        if src_str not in sys.path:
            sys.path.insert(0, src_str)


def _show_fatal_error(message: str) -> None:
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(0, message, "FictoVerse 启动器", 0x10)
        except Exception:
            pass
    else:
        print(message, file=sys.stderr)


if __name__ == "__main__":
    _prepend_src_to_path()
    try:
        from novel_world.launcher.gui import main

        main()
    except ImportError as exc:
        _show_fatal_error(
            f"缺少依赖：{exc}\n\n"
            "请双击项目根目录的 GUI启动器.bat，"
            "或在虚拟环境中执行：\n"
            'pip install -e ".[launcher]"'
        )
        sys.exit(1)
    except Exception as exc:
        _show_fatal_error(f"启动失败：{exc}")
        sys.exit(1)
