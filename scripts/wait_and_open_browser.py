"""Wait for the local web server to become ready, then open the default browser."""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from novel_world.launcher import bootstrap

TIMEOUT_SEC = 45


def main() -> int:
    deadline = time.monotonic() + TIMEOUT_SEC
    while time.monotonic() < deadline:
        status = bootstrap.get_status()
        if status.running and status.url:
            bootstrap.open_browser()
            return 0
        time.sleep(0.5)
    print("服务启动超时，请查看 logs/server-startup.log", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
