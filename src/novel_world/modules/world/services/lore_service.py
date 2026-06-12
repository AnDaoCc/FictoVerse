from __future__ import annotations

from novel_world.core.domain.timestamps import utc_now
from novel_world.core.exceptions import NotFoundError, ValidationError
from novel_world.infrastructure.repositories.sqlite_lore_repository import (
    SqliteLoreRepository,
    new_lore_entry,
)
from novel_world.modules.ai.services.lore_engine import LoreEngine
from novel_world.modules.world.domain.lore_entry import LoreEntry, LoreEntryId
from novel_world.modules.world.services.st_lore_codec import (
    export_st_world_info,
    parse_st_world_info,
    parse_st_world_info_bytes,
)


class LoreService:
    def __init__(self, repository: SqliteLoreRepository) -> None:
        self._repo = repository
        self._engine = LoreEngine()

    def list_entries(self, *, character_id: str | None = None, include_disabled: bool = False) -> list[LoreEntry]:
        entries = self._repo.list_all_admin(character_id=character_id)
        if include_disabled:
            return entries
        return [e for e in entries if e.enabled]

    def get(self, entry_id: LoreEntryId) -> LoreEntry:
        entry = self._repo.get(entry_id)
        if entry is None:
            raise NotFoundError(f"Lore 条目不存在: {entry_id}")
        return entry

    def save(self, entry: LoreEntry) -> LoreEntry:
        if entry.scope == "character" and not entry.character_id.strip():
            raise ValidationError("角色级 Lore 必须指定 character_id。")
        if not entry.content.strip():
            raise ValidationError("Lore 内容不能为空。")
        entry.updated_at = utc_now()
        if entry.created_at is None:
            entry.created_at = entry.updated_at
        self._repo.save(entry)
        return entry

    def create(
        self,
        *,
        scope: str = "world",
        character_id: str = "",
        keys: list[str] | None = None,
        content: str,
        constant: bool = False,
        selective: bool = True,
        recursive: bool = False,
        priority: int = 0,
        insertion_order: int = 0,
        position: str = "before_main",
        depth: int = 4,
        enabled: bool = True,
        comment: str = "",
    ) -> LoreEntry:
        entry = new_lore_entry(
            scope=scope,  # type: ignore[arg-type]
            character_id=character_id,
            keys=keys or [],
            content=content.strip(),
            constant=constant,
            selective=selective,
            recursive=recursive,
            priority=priority,
            insertion_order=insertion_order,
            position=position,  # type: ignore[arg-type]
            depth=depth,
            enabled=enabled,
            comment=comment,
            source="manual",
        )
        return self.save(entry)

    def delete(self, entry_id: LoreEntryId) -> None:
        self.get(entry_id)
        self._repo.delete(entry_id)

    def sync_from_character_book(self, character) -> int:
        """将角色卡 character_book 同步为 scope=character 的 lore 条目。"""
        card = (getattr(character, "metadata", None) or {}).get("card") or {}
        book_entries = self._engine.entries_from_character_book(
            card.get("character_book"), str(character.id)
        )
        existing = self._repo.list_all_admin(character_id=str(character.id))
        for item in existing:
            if item.source == "character_book" and item.character_id == str(character.id):
                self._repo.delete(item.id)

        count = 0
        for entry in book_entries:
            entry.source = "character_book"
            entry.scope = "character"
            entry.character_id = str(character.id)
            self._repo.save(entry)
            count += 1
        return count

    def import_st_world_info(
        self,
        data: bytes,
        *,
        scope: str = "world",
        character_id: str = "",
        mode: str = "merge",
    ) -> int:
        if scope == "character" and not character_id.strip():
            raise ValidationError("角色级 World Info 必须指定 character_id。")
        parsed = parse_st_world_info_bytes(data)
        entries = parse_st_world_info(
            parsed,
            scope=scope,
            character_id=character_id.strip(),
            source="st_import",
        )
        if not entries:
            raise ValidationError("未解析到有效 Lore 条目。")

        if mode == "replace":
            existing = self._repo.list_all_admin(
                character_id=character_id.strip() or None
            )
            for item in existing:
                if item.source == "character_book":
                    continue
                if item.scope != scope:
                    continue
                if scope == "character" and item.character_id != character_id.strip():
                    continue
                if item.source in ("manual", "st_import"):
                    self._repo.delete(item.id)

        existing_refs = {
            (e.source_ref, e.scope, e.character_id): e
            for e in self._repo.list_all_admin(character_id=character_id.strip() or None)
            if e.source == "st_import"
        }
        count = 0
        for entry in entries:
            key = (entry.source_ref, entry.scope, entry.character_id)
            prior = existing_refs.get(key)
            if prior and mode == "merge":
                entry.id = prior.id
                entry.created_at = prior.created_at
            self.save(entry)
            count += 1
        return count

    def export_st_world_info(
        self,
        *,
        scope: str | None = None,
        character_id: str | None = None,
    ) -> dict:
        entries = self._repo.list_all_admin(character_id=character_id)
        filtered: list[LoreEntry] = []
        for entry in entries:
            if scope and entry.scope != scope:
                continue
            if character_id and entry.scope == "character" and entry.character_id != character_id:
                continue
            if entry.source == "character_book":
                continue
            filtered.append(entry)
        return export_st_world_info(filtered)
