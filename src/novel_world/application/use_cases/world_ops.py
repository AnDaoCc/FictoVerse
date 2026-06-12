from __future__ import annotations

from pathlib import Path

from novel_world.application.use_cases.create_world import CreateWorldUseCase, world_session
from novel_world.bootstrap.app_factory import create_app
from novel_world.core.domain.ids import SaveId, WorldId
from novel_world.modules.save.domain.entities import SaveSlot


class LoadSaveUseCase:
    def __init__(self, base_dir: Path | None = None) -> None:
        self._app = create_app(base_dir)

    def execute(self, world_id: WorldId, save_id: SaveId) -> None:
        runtime = self._app.open_world(world_id)
        try:
            runtime.save.load_save(save_id)
            runtime.commit()
        except Exception:
            runtime.rollback()
            raise
        finally:
            runtime.close()


class CreateSaveUseCase:
    def __init__(self, base_dir: Path | None = None) -> None:
        self._app = create_app(base_dir)

    def execute(self, world_id: WorldId, slot_index: int, *, label: str = "") -> SaveSlot:
        runtime = self._app.open_world(world_id)
        try:
            slot = runtime.save.create_save(world_id, slot_index, label=label)
            runtime.commit()
            return slot
        except Exception:
            runtime.rollback()
            raise
        finally:
            runtime.close()


class ListWorldsUseCase:
    def __init__(self, base_dir: Path | None = None) -> None:
        self._app = create_app(base_dir)

    def execute(self) -> list[WorldId]:
        return self._app.list_world_ids()
