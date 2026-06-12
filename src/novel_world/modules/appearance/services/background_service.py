from __future__ import annotations

from pathlib import Path

from novel_world.bootstrap.config import AppConfig


ALLOWED_BG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


class BackgroundService:
    def __init__(self, config: AppConfig) -> None:
        self._config = config

    def save_session_background(
        self, session_id: str, file_bytes: bytes, filename: str
    ) -> str:
        ext = Path(filename or "bg.jpg").suffix.lower()
        if ext not in ALLOWED_BG_EXT:
            ext = ".jpg"
        dest_dir = self._config.session_background_dir(session_id)
        dest_dir.mkdir(parents=True, exist_ok=True)
        for old in dest_dir.glob("bg.*"):
            old.unlink(missing_ok=True)
        rel = f"backgrounds/{session_id}/bg{ext}"
        path = self._config.uploads_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(file_bytes)
        return rel

    def save_world_background(
        self, world_id: str, file_bytes: bytes, filename: str
    ) -> str:
        ext = Path(filename or "bg.jpg").suffix.lower()
        if ext not in ALLOWED_BG_EXT:
            ext = ".jpg"
        dest_dir = self._config.world_background_dir(world_id)
        dest_dir.mkdir(parents=True, exist_ok=True)
        for old in dest_dir.glob("bg.*"):
            old.unlink(missing_ok=True)
        rel = f"worlds/{world_id}/background/bg{ext}"
        path = self._config.uploads_dir / rel
        path.write_bytes(file_bytes)
        return rel

    def resolve_path(self, rel_path: str) -> Path | None:
        if not rel_path or ".." in rel_path:
            return None
        path = (self._config.uploads_dir / rel_path).resolve()
        try:
            path.relative_to(self._config.uploads_dir.resolve())
        except ValueError:
            return None
        return path if path.is_file() else None

    def public_url(self, rel_path: str) -> str:
        return f"/api/uploads/{rel_path.lstrip('/')}"
