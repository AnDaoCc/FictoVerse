from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from novel_world.bootstrap.config import AppConfig, default_config
from novel_world.core.domain.ids import WorldId
from novel_world.infrastructure.db.session import DatabaseSession, open_session
from novel_world.infrastructure.repositories.sqlite_lore_repository import SqliteLoreRepository
from novel_world.infrastructure.repositories.sqlite_repositories import (
    SqliteCharacterRepository,
    SqliteEventRepository,
    SqliteSaveRepository,
    SqliteStateRepository,
    SqliteWorldRepository,
)
from novel_world.modules.character.services.character_service import CharacterService
from novel_world.modules.event.services.event_service import EventService
from novel_world.modules.save.services.save_service import SaveService
from novel_world.modules.state.services.state_service import StateService
from novel_world.modules.world.services.lore_service import LoreService
from novel_world.modules.world.services.world_service import WorldService


@dataclass
class WorldRuntime:
    """单个世界数据库的运行时上下文。"""

    world_id: WorldId
    db_path: Path
    session: DatabaseSession
    world: WorldService
    character: CharacterService
    state: StateService
    event: EventService
    save: SaveService
    lore: LoreService

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()

    def close(self) -> None:
        self.session.close()


class AppFactory:
    def __init__(self, config: AppConfig | None = None) -> None:
        self.config = config or default_config()
        self.config.ensure_dirs()

    def open_world(self, world_id: WorldId) -> WorldRuntime:
        db_path = self.config.world_db_path(str(world_id))
        session = DatabaseSession(db_path)
        session.open()
        return self._build_runtime(world_id, db_path, session)

    def create_world_db(self, world_id: WorldId) -> WorldRuntime:
        return self.open_world(world_id)

    def _build_runtime(
        self, world_id: WorldId, db_path: Path, session: DatabaseSession
    ) -> WorldRuntime:
        conn = session.connection
        world_repo = SqliteWorldRepository(conn)
        character_repo = SqliteCharacterRepository(conn)
        state_repo = SqliteStateRepository(conn)
        event_repo = SqliteEventRepository(conn)
        save_repo = SqliteSaveRepository(conn)
        lore_repo = SqliteLoreRepository(conn)

        return WorldRuntime(
            world_id=world_id,
            db_path=db_path,
            session=session,
            world=WorldService(world_repo),
            character=CharacterService(character_repo),
            state=StateService(state_repo),
            event=EventService(event_repo),
            save=SaveService(
                self.config,
                world_repo,
                character_repo,
                state_repo,
                event_repo,
                save_repo,
            ),
            lore=LoreService(lore_repo),
        )

    def list_world_ids(self) -> list[WorldId]:
        if not self.config.active_dir.exists():
            return []
        ids: list[WorldId] = []
        for path in sorted(self.config.active_dir.glob("world_*.db")):
            world_id_str = path.stem.removeprefix("world_")
            ids.append(WorldId(world_id_str))
        return ids

    def delete_world(self, world_id: WorldId) -> bool:
        db_path = self.config.world_db_path(str(world_id))
        deleted = False
        for path in (db_path, db_path.with_suffix(db_path.suffix + "-wal"), db_path.with_suffix(db_path.suffix + "-shm")):
            if path.exists():
                path.unlink()
                deleted = True
        return deleted


def create_app(base_dir: Path | None = None) -> AppFactory:
    config = default_config(base_dir)
    return AppFactory(config)
