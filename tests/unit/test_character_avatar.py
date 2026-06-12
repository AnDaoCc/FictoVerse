from __future__ import annotations

import io

import pytest
from PIL import Image

from novel_world.application.use_cases.create_world import CreateWorldUseCase
from novel_world.bootstrap.app_factory import create_app
from novel_world.core.domain.ids import WorldId
from novel_world.infrastructure.repositories.sqlite_repositories import SqliteCharacterRepository
from novel_world.modules.character.services.character_card_service import CharacterCardService
from novel_world.modules.character.services.card_mapper import get_avatar_relpath


def _png_bytes(size: int = 64) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (size, size), color=(120, 80, 200)).save(buf, format="PNG")
    return buf.getvalue()


def test_save_avatar_from_bytes(tmp_path) -> None:
    world = CreateWorldUseCase(base_dir=tmp_path).execute("头像世界")
    factory = create_app(tmp_path)
    rt = factory.open_world(WorldId(str(world.id)))
    try:
        character = rt.character.create(WorldId(str(world.id)), "测试角色", role="npc")
        rt.session.commit()
        card_svc = CharacterCardService(
            factory.config,
            SqliteCharacterRepository(rt.session.connection),
        )
        data = _png_bytes(128)
        rel = card_svc.save_avatar_from_bytes(
            str(world.id), str(character.id), data, ext="png"
        )
        rt.session.commit()
        assert rel
        path = card_svc.character_avatar_path(str(world.id), str(character.id))
        assert path is not None and path.exists()
        saved = rt.character.get(character.id)
        assert get_avatar_relpath(saved) == rel
    finally:
        rt.close()


def test_resolve_avatar_redirect_safe_path() -> None:
    from novel_world.web.app import _resolve_avatar_redirect

    class _Req:
        headers: dict[str, str] = {}

    req = _Req()
    assert _resolve_avatar_redirect("/worlds/w1", "w1", "c1", req) == "/worlds/w1"
    assert (
        _resolve_avatar_redirect("//evil.com", "w1", "c1", req)
        == "/worlds/w1"
    )
