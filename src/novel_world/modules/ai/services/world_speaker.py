"""世界聊天：解析/推断 assistant 消息的说话角色。"""

from __future__ import annotations

import json
import re
from typing import Any

from novel_world.bootstrap.app_factory import AppFactory
from novel_world.core.domain.ids import CharacterId, WorldId
from novel_world.core.exceptions import NotFoundError
from novel_world.modules.character.character_roles import normalize_role
from novel_world.modules.ai.services.tts_voice_resolver import build_speaker_payload
from novel_world.modules.character.services.card_mapper import get_avatar_relpath


def _speaker_payload(character: Any, world_id: str) -> dict[str, str]:
    avatar_url = ""
    rel = get_avatar_relpath(character)
    if rel:
        avatar_url = f"/api/worlds/{world_id}/characters/{character.id}/avatar"
    return build_speaker_payload(character, world_id, avatar_url=avatar_url)


def _list_characters(world_app: AppFactory, world_id: str) -> list[Any]:
    rt = world_app.open_world(WorldId(world_id))
    try:
        chars = rt.character.list_by_world(WorldId(world_id), active_only=True)
        if not chars:
            chars = rt.character.list_by_world(WorldId(world_id), active_only=False)
        return list(chars)
    finally:
        rt.close()


def extract_json(raw: str) -> dict[str, Any] | None:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def infer_speaker_from_content(
    world_app: AppFactory,
    world_id: str,
    content: str,
    *,
    characters: list[Any] | None = None,
) -> dict[str, str] | None:
    text = (content or "").strip()
    if not text:
        return None
    chars = characters if characters is not None else _list_characters(world_app, world_id)
    if not chars:
        return None

    for c in sorted(chars, key=lambda x: len(x.name or ""), reverse=True):
        name = (c.name or "").strip()
        if len(name) >= 2 and name in text:
            return _speaker_payload(c, world_id)

    priority = (
        "hero_male",
        "hero_female",
        "party_male",
        "party_female",
        "npc_important",
        "npc_story",
        "npc_passerby",
    )
    by_role = {normalize_role(c.role): c for c in chars}
    for role_key in priority:
        if role_key in by_role:
            return _speaker_payload(by_role[role_key], world_id)

    return _speaker_payload(chars[0], world_id)


def parse_world_reply(
    world_app: AppFactory,
    world_id: str,
    raw: str,
    *,
    characters: list[Any] | None = None,
) -> tuple[dict[str, str] | None, str]:
    data = extract_json(raw)
    if data is None:
        inferred = infer_speaker_from_content(
            world_app, world_id, raw, characters=characters
        )
        return inferred, raw.strip()

    speaker_id = str(
        data.get("speaker_id")
        or data.get("character_id")
        or data.get("speaker")
        or ""
    ).strip()
    content = str(data.get("content") or data.get("text") or data.get("reply") or "").strip()
    if not content:
        inferred = infer_speaker_from_content(
            world_app, world_id, raw, characters=characters
        )
        return inferred, raw.strip()

    if speaker_id in ("", "narrator", "旁白"):
        return {
            "character_id": "",
            "world_id": world_id,
            "name": "旁白",
            "avatar_url": "",
        }, content

    chars = characters if characters is not None else _list_characters(world_app, world_id)
    for c in chars:
        if str(c.id) == speaker_id or (c.name or "").strip() == speaker_id:
            return _speaker_payload(c, world_id), content

    rt = world_app.open_world(WorldId(world_id))
    try:
        try:
            character = rt.character.get(CharacterId(speaker_id))
            return _speaker_payload(character, world_id), content
        except NotFoundError:
            pass
    finally:
        rt.close()

    inferred = infer_speaker_from_content(
        world_app, world_id, content, characters=chars
    )
    if inferred:
        return inferred, content
    return {
        "character_id": "",
        "world_id": world_id,
        "name": speaker_id or "路人",
        "avatar_url": "",
    }, content


def resolve_message_speaker(
    message: Any,
    world_id: str,
    world_app: AppFactory,
    characters: list[Any],
) -> dict[str, str] | None:
    speaker = getattr(message, "speaker", None)
    if isinstance(speaker, dict) and speaker.get("name"):
        if not speaker.get("avatar_url") and speaker.get("character_id"):
            for c in characters:
                if str(c.id) == str(speaker.get("character_id")):
                    return _speaker_payload(c, world_id)
        return {str(k): str(v) for k, v in speaker.items()}
    if getattr(message, "role", None) != "assistant":
        return None
    content = getattr(message, "content", "") or ""
    return infer_speaker_from_content(
        world_app, world_id, content, characters=characters
    )
