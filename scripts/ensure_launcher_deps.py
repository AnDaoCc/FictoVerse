"""CLI wrapper for launcher offline dependency install."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from novel_world.launcher.deps_install import install_launcher_deps_offline
from novel_world.launcher.bootstrap import get_root, _pip_subprocess_env


def main() -> int:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(sys.executable)
    root = get_root()
    ok = install_launcher_deps_offline(
        target,
        root,
        env=_pip_subprocess_env(root),
        log=print,
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
