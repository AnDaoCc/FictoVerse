from __future__ import annotations

from pathlib import Path

from novel_world.bootstrap.app_factory import AppFactory
from novel_world.bootstrap.config import AppConfig
from novel_world.core.domain.ids import CharacterId, WorldId
from novel_world.core.domain.timestamps import utc_now
from novel_world.core.exceptions import ValidationError
from novel_world.infrastructure.repositories.sqlite_lore_repository import SqliteLoreRepository
from novel_world.modules.character.domain.character_card import CharacterCard
from novel_world.modules.character.domain.entities import Character
from novel_world.modules.character.ports.character_repository import CharacterRepository
from novel_world.modules.character.services.card_codec import (
    card_from_json_bytes,
    card_from_json_bytes_with_warnings,
    card_from_png_bytes,
    card_from_png_bytes_with_warnings,
    card_to_json_bytes,
    card_to_png_bytes,
)
from novel_world.modules.character.services.card_mapper import (
    apply_card_to_character,
    avatar_relpath,
    card_from_character,
    get_avatar_relpath,
)
from novel_world.modules.world.services.lore_service import LoreService


class CharacterCardService:
    def __init__(self, config: AppConfig, repository: CharacterRepository) -> None:
        self._config = config
        self._repository = repository

    def character_avatar_dir(self, world_id: str, character_id: str) -> Path:
        return self._config.character_avatar_dir(world_id, character_id)

    def character_avatar_path(self, world_id: str, character_id: str) -> Path | None:
        character = self._repository.get(CharacterId(character_id))
        if character is None:
            return None
        rel = get_avatar_relpath(character)
        if not rel:
            return None
        path = self._config.uploads_dir / rel
        return path if path.exists() else None

    def avatar_url(self, world_id: str, character_id: str) -> str:
        return f"/api/worlds/{world_id}/characters/{character_id}/avatar"

    def import_card(
        self,
        world_id: WorldId,
        character_id: CharacterId,
        file_bytes: bytes,
        filename: str,
    ) -> tuple[Character, list[str]]:
        card, warnings, png_bytes = self._parse_card_file(file_bytes, filename)
        character = self._apply_and_save(world_id, character_id, card)
        if png_bytes:
            self.save_avatar_from_bytes(world_id, character_id, png_bytes, ext="png")
        return character, warnings

    def import_card_as_new_character(
        self, world_id: WorldId, file_bytes: bytes, filename: str
    ) -> tuple[Character, list[str]]:
        card, warnings, png_bytes = self._parse_card_file(file_bytes, filename)

        if not card.name.strip():
            raise ValidationError("角色卡缺少名称。")

        from novel_world.core.domain.ids import new_character_id

        now = utc_now()
        character = Character(
            id=new_character_id(),
            world_id=world_id,
            name=card.name.strip(),
            role="npc",
            profile={},
            attributes={},
            metadata={},
            created_at=now,
            updated_at=now,
        )
        apply_card_to_character(character, card)
        character.updated_at = utc_now()
        self._repository.save(character)
        self._sync_lore_from_card(world_id, character)
        if png_bytes:
            self.save_avatar_from_bytes(world_id, character.id, png_bytes, ext="png")
        return character, warnings

    def _parse_card_file(
        self, file_bytes: bytes, filename: str
    ) -> tuple[CharacterCard, list[str], bytes | None]:
        lower = (filename or "").lower()
        if lower.endswith(".png"):
            card, warnings, png_bytes = card_from_png_bytes_with_warnings(file_bytes)
            return card, warnings, png_bytes
        if lower.endswith(".json"):
            card, warnings = card_from_json_bytes_with_warnings(file_bytes)
            return card, warnings, None
        try:
            card, warnings = card_from_json_bytes_with_warnings(file_bytes)
            return card, warnings, None
        except ValidationError:
            card, warnings, png_bytes = card_from_png_bytes_with_warnings(file_bytes)
            return card, warnings, png_bytes

    def export_json(self, character: Character, *, prefer_v3: bool = True) -> bytes:
        from novel_world.modules.character.services.card_v3_codec import card_to_json_bytes as v3_export

        return v3_export(card_from_character(character), prefer_v3=prefer_v3)

    def export_png(self, character: Character, world_id: str) -> bytes:
        card = card_from_character(character)
        avatar_path = self.character_avatar_path(world_id, str(character.id))
        image_bytes = avatar_path.read_bytes() if avatar_path else None
        return card_to_png_bytes(card, image_bytes)

    def save_avatar_from_bytes(
        self,
        world_id: WorldId | str,
        character_id: CharacterId | str,
        data: bytes,
        *,
        ext: str = "png",
    ) -> str:
        wid, cid = str(world_id), str(character_id)
        dest_dir = self.character_avatar_dir(wid, cid)
        dest_dir.mkdir(parents=True, exist_ok=True)
        rel = avatar_relpath(wid, cid, ext)
        dest = self._config.uploads_dir / rel
        dest.write_bytes(data)

        character = self._repository.get(CharacterId(cid))
        if character is None:
            raise ValidationError(f"角色不存在: {cid}")
        metadata = dict(character.metadata or {})
        metadata["avatar_path"] = rel
        character.metadata = metadata
        character.updated_at = utc_now()
        self._repository.save(character)
        return rel

    def _apply_and_save(
        self, world_id: WorldId, character_id: CharacterId, card: CharacterCard
    ) -> Character:
        character = self._repository.get(character_id)
        if character is None:
            raise ValidationError(f"角色不存在: {character_id}")
        if str(character.world_id) != str(world_id):
            raise ValidationError("角色不属于该世界。")
        apply_card_to_character(character, card)
        character.updated_at = utc_now()
        self._repository.save(character)
        self._sync_lore_from_card(world_id, character)
        return character

    def _sync_lore_from_card(self, world_id: WorldId, character: Character) -> None:
        factory = AppFactory(self._config)
        rt = factory.open_world(WorldId(str(world_id)))
        try:
            LoreService(SqliteLoreRepository(rt.session.connection)).sync_from_character_book(
                character
            )
            rt.session.commit()
        finally:
            rt.close()
