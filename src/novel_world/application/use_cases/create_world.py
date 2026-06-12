from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from novel_world.bootstrap.app_factory import AppFactory, WorldRuntime, create_app
from novel_world.core.domain.ids import WorldId, new_world_id
from novel_world.modules.world.domain.entities import World


@contextmanager
def world_session(base_dir: Path | None, world_id: WorldId) -> Iterator[WorldRuntime]:
    app = create_app(base_dir)
    runtime = app.open_world(world_id)
    try:
        yield runtime
        runtime.commit()
    except Exception:
        runtime.rollback()
        raise
    finally:
        runtime.close()


class CreateWorldUseCase:
    def __init__(self, app: AppFactory | None = None, base_dir: Path | None = None) -> None:
        self._app = app or create_app(base_dir)

    def execute(
        self,
        name: str,
        *,
        description: str = "",
        genre: str = "",
        rules: dict[str, Any] | None = None,
        settings: dict[str, Any] | None = None,
    ) -> World:
        world_id = new_world_id()
        runtime = self._app.open_world(world_id)
        try:
            world = runtime.world.create(
                name,
                world_id=world_id,
                description=description,
                genre=genre,
                rules=rules,
                settings=settings,
            )
            runtime.state.set_value(world.id, "time.current", "故事尚未开始", scope="world")
            runtime.event.record(
                world.id,
                "system.world_created",
                payload={"name": world.name},
            )
            runtime.commit()
            return world
        except Exception:
            runtime.rollback()
            raise
        finally:
            runtime.close()
