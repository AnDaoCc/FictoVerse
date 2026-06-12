from __future__ import annotations

import atexit
import os
import socket
from pathlib import Path
import sys

import uvicorn

from novel_world.bootstrap.config import default_config, project_root
from novel_world.infrastructure.server_meta import remove_server_meta


def resolve_root() -> Path:
    env_root = os.environ.get("NOVEL_WORLD_ROOT", "").strip()
    if env_root:
        path = Path(env_root).resolve()
        if (path / "pyproject.toml").is_file():
            return path
    return project_root()


PROJECT_ROOT = resolve_root()


def _ensure_stdio() -> None:
    """pythonw.exe 会把 stdout/stderr 设为 None，uvicorn 日志初始化会因此崩溃。"""
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115


def _pick_free_port(host: str = "127.0.0.1") -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return int(s.getsockname()[1])


def main() -> None:
    _ensure_stdio()
    os.chdir(PROJECT_ROOT)
    config = default_config(PROJECT_ROOT)
    config.ensure_dirs()

    host = "127.0.0.1"
    port = _pick_free_port(host)

    os.environ["NOVEL_WORLD_SERVER_HOST"] = host
    os.environ["NOVEL_WORLD_SERVER_PORT"] = str(port)
    atexit.register(remove_server_meta, config.data_dir)

    uvicorn.run(
        "novel_world.web.app:app",
        host=host,
        port=port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
