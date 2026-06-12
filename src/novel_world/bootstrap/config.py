from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    """本地路径与版本配置。"""

    data_dir: Path
    schema_version: int = 1
    snapshot_version: int = 1
    default_locale: str = "zh"

    @property
    def active_dir(self) -> Path:
        return self.data_dir / "active"

    @property
    def saves_dir(self) -> Path:
        return self.data_dir / "saves"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    def world_documents_dir(self, world_id: str) -> Path:
        return self.uploads_dir / "worlds" / world_id / "documents"

    def chat_session_uploads_dir(self, session_id: str) -> Path:
        return self.uploads_dir / "chat" / session_id

    def character_avatar_dir(self, world_id: str, character_id: str) -> Path:
        return self.uploads_dir / "worlds" / world_id / "characters" / character_id

    def session_background_dir(self, session_id: str) -> Path:
        return self.uploads_dir / "backgrounds" / session_id

    def world_background_dir(self, world_id: str) -> Path:
        return self.uploads_dir / "worlds" / world_id / "background"

    @property
    def extensions_dir(self) -> Path:
        return self.data_dir / "extensions"

    @property
    def mods_dir(self) -> Path:
        return self.data_dir / "mods"

    @property
    def world_packs_dir(self) -> Path:
        return self.data_dir / "packs"

    def world_db_path(self, world_id: str) -> Path:
        return self.active_dir / f"world_{world_id}.db"

    def snapshot_path(self, save_id: str) -> Path:
        return self.saves_dir / f"{save_id}.snapshot.json"

    @property
    def app_db_path(self) -> Path:
        return self.data_dir / "app.db"

    @property
    def server_meta_path(self) -> Path:
        return self.data_dir / "server.json"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.active_dir.mkdir(parents=True, exist_ok=True)
        self.saves_dir.mkdir(parents=True, exist_ok=True)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.extensions_dir.mkdir(parents=True, exist_ok=True)
        self.mods_dir.mkdir(parents=True, exist_ok=True)
        self.world_packs_dir.mkdir(parents=True, exist_ok=True)


def project_root() -> Path:
    """项目根目录（向上搜索含 pyproject.toml 的目录）。"""
    start = Path(__file__).resolve()
    for parent in [start, *start.parents]:
        if (parent / "pyproject.toml").is_file():
            return parent
    return start.parents[3]  # fallback


def default_config(base_dir: Path | None = None) -> AppConfig:
    root = base_dir or project_root()
    return AppConfig(data_dir=root / "data")
