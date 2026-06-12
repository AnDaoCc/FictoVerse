"""启动器世界管理：直连本地数据库，与 Web 世界详情页能力对齐。"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from novel_world.application.use_cases.create_world import CreateWorldUseCase
from novel_world.bootstrap.app_context import create_app_context
from novel_world.bootstrap.app_factory import create_app
from novel_world.bootstrap.config import default_config
from novel_world.core.domain.ids import CharacterId, SaveId, WorldId
from novel_world.core.exceptions import DomainError, ValidationError
from novel_world.infrastructure.repositories.sqlite_repositories import SqliteCharacterRepository
from novel_world.modules.ai.services.user_persona import persona_from_world_settings, store_persona
from novel_world.modules.character.services.card_mapper import card_from_character
from novel_world.modules.character.services.character_card_service import CharacterCardService
from novel_world.launcher.bootstrap import get_root
from novel_world.modules.character.character_roles import normalize_role


def _json_loads_maybe(text: str, *, default: Any) -> Any:
    text = (text or "").strip()
    if not text:
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ValidationError(f"JSON 格式不正确：{e.msg}") from e


def _normalize_relationships(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    cleaned: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        target = str(item.get("target", "")).strip()
        if not target:
            continue
        cleaned.append(
            {
                "target": target,
                "type": str(item.get("type", "")).strip(),
                "note": str(item.get("note", "")).strip(),
            }
        )
    return cleaned


def _parse_keys_field(raw: str) -> list[str]:
    if not raw.strip():
        return []
    parts = [p.strip() for p in raw.replace("，", ",").split(",")]
    return [p for p in parts if p]


def _decode_b64(data_b64: str) -> bytes:
    text = (data_b64 or "").strip()
    if "," in text:
        text = text.split(",", 1)[1]
    return base64.b64decode(text)


def _ok(data: Any = None, message: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {"ok": True}
    if message:
        out["message"] = message
    if data is not None:
        out["data"] = data
    return out


def _err(message: str) -> dict[str, Any]:
    return {"ok": False, "message": message}


def _root() -> Path:
    return get_root()


def _app_factory():
    return create_app(_root())


def _app_ctx():
    return create_app_context(_root())


def _clear_world_cache(world_id: str) -> None:
    ctx = _app_ctx()
    runtime = ctx.open()
    try:
        runtime.chat.clear_world_cache(world_id)
        runtime.commit()
    finally:
        runtime.close()


def _world_background_rel(world_id: str) -> str:
    app_factory = _app_factory()
    rt = app_factory.open_world(WorldId(world_id))
    try:
        world = rt.world.get(WorldId(world_id))
        settings = world.settings if isinstance(world.settings, dict) else {}
        return str(settings.get("background") or "").strip()
    finally:
        rt.close()


def _character_dict(character: Any) -> dict[str, Any]:
    profile = character.profile if isinstance(character.profile, dict) else {}
    metadata = character.metadata if isinstance(character.metadata, dict) else {}
    return {
        "id": str(character.id),
        "name": character.name,
        "role": character.role or "npc",
        "profile": profile,
        "attributes": character.attributes if isinstance(character.attributes, dict) else {},
        "metadata": metadata,
        "relationships": metadata.get("relationships") or [],
        "is_active": bool(character.is_active),
    }


def list_worlds() -> dict[str, Any]:
    app_factory = _app_factory()
    worlds: list[dict[str, Any]] = []
    for wid in app_factory.list_world_ids():
        rt = app_factory.open_world(wid)
        try:
            w = rt.world.get(wid)
            desc = (w.description or "").strip()
            worlds.append(
                {
                    "id": str(w.id),
                    "name": w.name,
                    "genre": w.genre or "",
                    "description_preview": desc[:60] + ("…" if len(desc) > 60 else ""),
                }
            )
        except DomainError:
            worlds.append({"id": str(wid), "name": f"(损坏) {wid}", "genre": "", "description_preview": ""})
        finally:
            rt.close()
    return _ok(worlds)


def get_world(world_id: str) -> dict[str, Any]:
    app_factory = _app_factory()
    ctx = _app_ctx()
    runtime = ctx.open()
    rt = app_factory.open_world(WorldId(world_id))
    try:
        world = rt.world.get(WorldId(world_id))
        characters = rt.character.list_by_world(world.id, active_only=False)
        state_entries = rt.state.list_by_world(world.id)
        saves = rt.save.list_saves(world.id)
        lore_entries = rt.lore.list_entries(include_disabled=True)
        documents = runtime.documents.list_world_documents(world_id)
        settings = world.settings if isinstance(world.settings, dict) else {}
        persona = persona_from_world_settings(settings)
        bg_rel = str(settings.get("background") or "").strip()
        data = {
            "id": str(world.id),
            "name": world.name,
            "genre": world.genre or "",
            "description": world.description or "",
            "rules": world.rules if isinstance(world.rules, dict) else {},
            "settings": settings,
            "rules_json": json.dumps(world.rules or {}, ensure_ascii=False, indent=2),
            "settings_json": json.dumps(settings or {}, ensure_ascii=False, indent=2),
            "user_persona": {
                "name": persona.get("name", ""),
                "description": persona.get("description", ""),
            },
            "has_background": bool(bg_rel),
            "background_rel": bg_rel,
            "characters": [_character_dict(c) for c in characters],
            "state_entries": [
                {
                    "scope": e.scope,
                    "scope_id": str(e.scope_id) if e.scope_id else "",
                    "key": e.key,
                    "value": e.value,
                }
                for e in state_entries
            ],
            "documents": [
                {"id": d.id, "filename": d.filename, "mime_type": d.mime_type or ""}
                for d in documents
            ],
            "lore_entries": [
                {
                    "id": e.id,
                    "scope": e.scope,
                    "character_id": e.character_id,
                    "keys": e.keys,
                    "content": e.content,
                    "constant": e.constant,
                    "selective": e.selective,
                    "recursive": e.recursive,
                    "priority": e.priority,
                    "insertion_order": e.insertion_order,
                    "position": e.position,
                    "depth": e.depth,
                    "enabled": e.enabled,
                    "comment": e.comment,
                    "source": e.source,
                }
                for e in lore_entries
            ],
            "saves": [
                {
                    "id": str(s.id),
                    "slot_index": s.slot_index,
                    "label": s.label,
                    "created_at": s.created_at.isoformat() if s.created_at else "",
                }
                for s in saves
            ],
        }
        return _ok(data)
    except DomainError as e:
        return _err(str(e))
    finally:
        rt.close()
        runtime.close()


def create_world(
    name: str,
    description: str = "",
    genre: str = "",
    rules_json: str = "{}",
    settings_json: str = "{}",
) -> dict[str, Any]:
    try:
        rules = _json_loads_maybe(rules_json, default={})
        settings = _json_loads_maybe(settings_json, default={})
        world = CreateWorldUseCase(base_dir=_root()).execute(
            name, description=description, genre=genre, rules=rules, settings=settings
        )
        return _ok({"id": str(world.id), "name": world.name}, "世界已创建")
    except (ValidationError, DomainError) as e:
        return _err(str(e))


def update_world(
    world_id: str,
    name: str,
    description: str = "",
    genre: str = "",
    rules_json: str = "{}",
    settings_json: str = "{}",
) -> dict[str, Any]:
    app_factory = _app_factory()
    rt = app_factory.open_world(WorldId(world_id))
    try:
        rules = _json_loads_maybe(rules_json, default={})
        settings = _json_loads_maybe(settings_json, default={})
        existing = rt.world.get(WorldId(world_id))
        old_settings = existing.settings if isinstance(existing.settings, dict) else {}
        if "background" in old_settings and "background" not in settings:
            settings["background"] = old_settings["background"]
        rt.world.update(
            WorldId(world_id),
            name=name,
            description=description,
            genre=genre,
            rules=rules,
            settings=settings,
        )
        rt.session.commit()
        _clear_world_cache(world_id)
        return _ok(message="世界已保存")
    except (ValidationError, DomainError) as e:
        rt.session.rollback()
        return _err(str(e))
    finally:
        rt.close()


def delete_world(world_id: str) -> dict[str, Any]:
    app_factory = _app_factory()
    app_factory.delete_world(WorldId(world_id))
    ctx = _app_ctx()
    runtime = ctx.open()
    try:
        runtime.chat.delete_sessions_by_world(world_id)
        runtime.commit()
    finally:
        runtime.close()
    return _ok(message="世界已删除")


def update_world_user_persona(
    world_id: str,
    persona_name: str = "",
    persona_description: str = "",
) -> dict[str, Any]:
    app_factory = _app_factory()
    rt = app_factory.open_world(WorldId(world_id))
    try:
        world = rt.world.get(WorldId(world_id))
        settings = dict(world.settings) if isinstance(world.settings, dict) else {}
        settings["user_persona"] = store_persona(persona_name, persona_description)
        rt.world.update(WorldId(world_id), settings=settings)
        rt.session.commit()
        _clear_world_cache(world_id)
        return _ok(message="世界默认人设已保存")
    except DomainError as e:
        return _err(str(e))
    finally:
        rt.close()


def upload_world_background(world_id: str, filename: str, data_b64: str) -> dict[str, Any]:
    app_factory = _app_factory()
    ctx = _app_ctx()
    runtime = ctx.open()
    rt = app_factory.open_world(WorldId(world_id))
    try:
        data = _decode_b64(data_b64)
        world = rt.world.get(WorldId(world_id))
        settings = dict(world.settings or {}) if isinstance(world.settings, dict) else {}
        rel = runtime.background.save_world_background(world_id, data, filename or "bg.png")
        settings["background"] = rel
        rt.world.update(
            WorldId(world_id),
            name=world.name,
            description=world.description,
            genre=world.genre,
            rules=world.rules,
            settings=settings,
        )
        rt.session.commit()
        runtime.commit()
        return _ok(message="世界背景已更新")
    except Exception as e:
        rt.session.rollback()
        return _err(str(e))
    finally:
        rt.close()
        runtime.close()


def clear_world_background(world_id: str) -> dict[str, Any]:
    app_factory = _app_factory()
    ctx = _app_ctx()
    runtime = ctx.open()
    rt = app_factory.open_world(WorldId(world_id))
    try:
        world = rt.world.get(WorldId(world_id))
        settings = dict(world.settings or {}) if isinstance(world.settings, dict) else {}
        old = str(settings.pop("background", "") or "").strip()
        if old:
            old_path = runtime.background.resolve_path(old)
            if old_path:
                old_path.unlink(missing_ok=True)
        rt.world.update(
            WorldId(world_id),
            name=world.name,
            description=world.description,
            genre=world.genre,
            rules=world.rules,
            settings=settings,
        )
        rt.session.commit()
        return _ok(message="世界背景已清除")
    except Exception as e:
        return _err(str(e))
    finally:
        rt.close()
        runtime.close()


def import_world_pack(filename: str, data_b64: str) -> dict[str, Any]:
    ctx = _app_ctx()
    runtime = ctx.open()
    try:
        data = _decode_b64(data_b64)
        result = runtime.world_pack.import_world(data)
        runtime.commit()
        return _ok({"world_id": result["world_id"]}, f"已导入世界包：{filename or 'pack.zip'}")
    except Exception as e:
        runtime.rollback()
        return _err(str(e))
    finally:
        runtime.close()


def export_world_pack(world_id: str, include_uploads: bool = True) -> dict[str, Any]:
    ctx = _app_ctx()
    runtime = ctx.open()
    try:
        data = runtime.world_pack.export_world(
            world_id, include_uploads=include_uploads
        )
        return _ok(
            {
                "filename": f"{world_id}.nworld.zip",
                "data_b64": base64.b64encode(data).decode("ascii"),
            }
        )
    except Exception as e:
        return _err(str(e))
    finally:
        runtime.close()


def create_character(world_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    app_factory = _app_factory()
    rt = app_factory.open_world(WorldId(world_id))
    try:
        profile = {
            k: str(payload.get(k, "")).strip()
            for k in ("summary", "personality", "appearance", "background")
            if str(payload.get(k, "")).strip()
        }
        attributes = payload.get("attributes") or {}
        if isinstance(attributes, str):
            attributes = _json_loads_maybe(attributes, default={})
        char = rt.character.create(
            WorldId(world_id),
            str(payload.get("name", "")).strip(),
            role=normalize_role(str(payload.get("role", "npc"))),
            profile=profile,
            attributes=attributes,
        )
        rt.session.commit()
        _clear_world_cache(world_id)
        return _ok(_character_dict(char), "角色已创建")
    except (ValidationError, DomainError) as e:
        return _err(str(e))
    finally:
        rt.close()


def update_character(world_id: str, character_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    app_factory = _app_factory()
    rt = app_factory.open_world(WorldId(world_id))
    try:
        existing = rt.character.get(CharacterId(character_id))
        existing_profile = dict(existing.profile or {})
        profile = {
            k: str(payload.get(k, "")).strip()
            for k in (
                "summary",
                "personality",
                "appearance",
                "background",
                "scenario",
                "first_mes",
                "mes_example",
                "post_history_instructions",
            )
            if str(payload.get(k, "")).strip()
            or k in ("scenario", "first_mes", "mes_example", "post_history_instructions")
        }
        if str(payload.get("summary", "")).strip():
            profile["description"] = str(payload.get("summary", "")).strip()
        elif existing_profile.get("description"):
            profile["description"] = existing_profile["description"]
        for key, val in existing_profile.items():
            if key not in profile and val:
                profile[key] = val
        attributes = payload.get("attributes") or existing.attributes or {}
        if isinstance(attributes, str):
            attributes = _json_loads_maybe(attributes, default={})
        metadata = dict(existing.metadata or {})
        rel_raw = payload.get("relationships_json") or payload.get("relationships") or []
        if isinstance(rel_raw, str):
            rel_raw = _json_loads_maybe(rel_raw, default=[])
        metadata["relationships"] = _normalize_relationships(rel_raw)
        rt.character.update(
            CharacterId(character_id),
            name=str(payload.get("name", existing.name)).strip(),
            role=normalize_role(str(payload.get("role", existing.role))),
            profile=profile,
            attributes=attributes,
            metadata=metadata,
        )
        updated = rt.character.get(CharacterId(character_id))
        meta2 = dict(updated.metadata or {})
        meta2["card"] = card_from_character(updated).to_v2_dict()
        rt.character.update(CharacterId(character_id), metadata=meta2)
        rt.session.commit()
        _clear_world_cache(world_id)
        return _ok(_character_dict(updated), "角色已保存")
    except (ValidationError, DomainError) as e:
        return _err(str(e))
    finally:
        rt.close()


def delete_character(world_id: str, character_id: str) -> dict[str, Any]:
    app_factory = _app_factory()
    rt = app_factory.open_world(WorldId(world_id))
    try:
        rt.character.delete(CharacterId(character_id))
        rt.session.commit()
        _clear_world_cache(world_id)
        return _ok(message="角色已删除")
    except DomainError as e:
        return _err(str(e))
    finally:
        rt.close()


def upload_character_avatar(
    world_id: str, character_id: str, filename: str, data_b64: str
) -> dict[str, Any]:
    app_factory = _app_factory()
    rt = app_factory.open_world(WorldId(world_id))
    try:
        config = default_config(_root())
        card_svc = CharacterCardService(config, SqliteCharacterRepository(rt.session.connection))
        data = _decode_b64(data_b64)
        ext = "png"
        fn = (filename or "").lower()
        if fn.endswith(".jpg") or fn.endswith(".jpeg"):
            ext = "jpg"
        elif fn.endswith(".webp"):
            ext = "webp"
        elif fn.endswith(".gif"):
            ext = "gif"
        card_svc.save_avatar_from_bytes(world_id, character_id, data, ext=ext)
        rt.session.commit()
        return _ok(message="头像已更新")
    except Exception as e:
        return _err(str(e))
    finally:
        rt.close()


def import_character_card(world_id: str, character_id: str, filename: str, data_b64: str) -> dict[str, Any]:
    app_factory = _app_factory()
    rt = app_factory.open_world(WorldId(world_id))
    try:
        config = default_config(_root())
        card_svc = CharacterCardService(config, SqliteCharacterRepository(rt.session.connection))
        data = _decode_b64(data_b64)
        _, warnings = card_svc.import_card(
            WorldId(world_id), CharacterId(character_id), data, filename or "card.json"
        )
        rt.session.commit()
        _clear_world_cache(world_id)
        updated = rt.character.get(CharacterId(character_id))
        msg = "角色卡已导入"
        if warnings:
            msg += "（" + "；".join(warnings) + "）"
        return _ok(_character_dict(updated), msg)
    except Exception as e:
        return _err(str(e))
    finally:
        rt.close()


def export_character_card(world_id: str, character_id: str, fmt: str = "json") -> dict[str, Any]:
    app_factory = _app_factory()
    rt = app_factory.open_world(WorldId(world_id))
    try:
        config = default_config(_root())
        card_svc = CharacterCardService(config, SqliteCharacterRepository(rt.session.connection))
        character = rt.character.get(CharacterId(character_id))
        if fmt == "png":
            data = card_svc.export_png(character, world_id)
            ext = "png"
        else:
            data = card_svc.export_json(character)
            ext = "json"
        return _ok(
            {
                "filename": f"{character.name}.{ext}",
                "data_b64": base64.b64encode(data).decode("ascii"),
            }
        )
    except Exception as e:
        return _err(str(e))
    finally:
        rt.close()


def set_state(
    world_id: str,
    key: str,
    value_json: str = "",
    scope: str = "world",
    scope_id: str = "",
) -> dict[str, Any]:
    app_factory = _app_factory()
    rt = app_factory.open_world(WorldId(world_id))
    try:
        value: Any = "" if not value_json.strip() else _json_loads_maybe(value_json, default="")
        character_id = CharacterId(scope_id) if scope == "character" and scope_id.strip() else None
        rt.state.set_value(
            WorldId(world_id), key, value, scope=scope, scope_id=character_id  # type: ignore[arg-type]
        )
        rt.session.commit()
        return _ok(message="状态已更新")
    except (ValidationError, DomainError) as e:
        return _err(str(e))
    finally:
        rt.close()


def upload_world_document(world_id: str, filename: str, data_b64: str) -> dict[str, Any]:
    ctx = _app_ctx()
    runtime = ctx.open()
    try:
        data = _decode_b64(data_b64)
        runtime.documents.upload_world_document(world_id, filename or "document.txt", data)
        runtime.commit()
        return _ok(message="文档已上传")
    except Exception as e:
        runtime.rollback()
        return _err(str(e))
    finally:
        runtime.close()


def delete_world_document(world_id: str, doc_id: str) -> dict[str, Any]:
    ctx = _app_ctx()
    runtime = ctx.open()
    try:
        runtime.documents.delete_world_document(doc_id)
        runtime.commit()
        return _ok(message="文档已删除")
    except Exception as e:
        return _err(str(e))
    finally:
        runtime.close()


def create_lore_entry(world_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    from novel_world.infrastructure.repositories.sqlite_lore_repository import new_lore_entry

    app_factory = _app_factory()
    rt = app_factory.open_world(WorldId(world_id))
    try:
        entry = new_lore_entry(
            scope=str(payload.get("scope", "world")),
            character_id=str(payload.get("character_id", "")).strip(),
            keys=_parse_keys_field(str(payload.get("keys", ""))),
            content=str(payload.get("content", "")).strip(),
            constant=bool(payload.get("constant")),
            selective=payload.get("selective", True) is not False,
            recursive=bool(payload.get("recursive")),
            priority=int(payload.get("priority") or 0),
            insertion_order=int(payload.get("insertion_order") or 0),
            position=str(payload.get("position") or "before_main"),
            depth=int(payload.get("depth") or 4),
            enabled=payload.get("enabled", True) is not False,
            comment=str(payload.get("comment", "")).strip(),
            source="manual",
        )
        rt.lore.save(entry)
        rt.session.commit()
        return _ok({"id": entry.id}, "Lore 已创建")
    except Exception as e:
        return _err(str(e))
    finally:
        rt.close()


def update_lore_entry(world_id: str, entry_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    from novel_world.core.domain.timestamps import utc_now

    app_factory = _app_factory()
    rt = app_factory.open_world(WorldId(world_id))
    try:
        entry = rt.lore.get(entry_id)
        if entry.source == "character_book":
            return _err("角色书来源的 Lore 不可编辑")
        entry.scope = str(payload.get("scope", entry.scope))
        entry.character_id = str(payload.get("character_id", "")).strip()
        entry.keys = _parse_keys_field(str(payload.get("keys", "")))
        entry.content = str(payload.get("content", "")).strip()
        entry.constant = bool(payload.get("constant"))
        entry.selective = payload.get("selective", True) is not False
        entry.recursive = bool(payload.get("recursive"))
        entry.priority = int(payload.get("priority") or 0)
        entry.insertion_order = int(payload.get("insertion_order") or 0)
        entry.position = str(payload.get("position") or "before_main")
        entry.depth = int(payload.get("depth") or 4)
        entry.enabled = payload.get("enabled", True) is not False
        entry.comment = str(payload.get("comment", "")).strip()
        entry.updated_at = utc_now()
        rt.lore.save(entry)
        rt.session.commit()
        return _ok(message="Lore 已保存")
    except Exception as e:
        return _err(str(e))
    finally:
        rt.close()


def import_st_world_info(
    world_id: str,
    filename: str,
    data_b64: str,
    scope: str = "world",
    character_id: str = "",
    mode: str = "merge",
) -> dict[str, Any]:
    app_factory = _app_factory()
    rt = app_factory.open_world(WorldId(world_id))
    try:
        data = _decode_b64(data_b64)
        count = rt.lore.import_st_world_info(
            data,
            scope=scope or "world",
            character_id=character_id or "",
            mode=mode or "merge",
        )
        rt.session.commit()
        _clear_world_cache(world_id)
        return _ok({"count": count}, f"已导入 {count} 条 World Info")
    except Exception as e:
        return _err(str(e))
    finally:
        rt.close()


def export_st_world_info(
    world_id: str,
    scope: str = "",
    character_id: str = "",
) -> dict[str, Any]:
    import base64
    import json

    app_factory = _app_factory()
    rt = app_factory.open_world(WorldId(world_id))
    try:
        payload = rt.lore.export_st_world_info(
            scope=scope or None,
            character_id=character_id or None,
        )
        raw = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        return _ok(
            {
                "filename": f"world_info_{world_id}.json",
                "data_b64": base64.b64encode(raw).decode("ascii"),
            }
        )
    except Exception as e:
        return _err(str(e))
    finally:
        rt.close()


def delete_lore_entry(world_id: str, entry_id: str) -> dict[str, Any]:
    app_factory = _app_factory()
    rt = app_factory.open_world(WorldId(world_id))
    try:
        entry = rt.lore.get(entry_id)
        if entry.source != "character_book":
            rt.lore.delete(entry_id)
            rt.session.commit()
        return _ok(message="Lore 已删除")
    except Exception as e:
        return _err(str(e))
    finally:
        rt.close()


def create_save(world_id: str, slot_index: int, label: str = "") -> dict[str, Any]:
    app_factory = _app_factory()
    rt = app_factory.open_world(WorldId(world_id))
    try:
        slot = rt.save.create_save(WorldId(world_id), slot_index, label=label)
        rt.session.commit()
        return _ok({"id": str(slot.id)}, "存档已创建")
    except Exception as e:
        return _err(str(e))
    finally:
        rt.close()


def load_save(world_id: str, save_id: str) -> dict[str, Any]:
    app_factory = _app_factory()
    rt = app_factory.open_world(WorldId(world_id))
    try:
        rt.save.load_save(SaveId(save_id))
        rt.session.commit()
        return _ok(message="存档已加载")
    except Exception as e:
        return _err(str(e))
    finally:
        rt.close()
