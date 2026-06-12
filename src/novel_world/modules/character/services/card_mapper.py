from __future__ import annotations

from typing import Any

from novel_world.modules.character.domain.character_card import CharacterCard
from novel_world.modules.character.domain.entities import Character
from novel_world.modules.ai.services.tts_voice_resolver import (
    extract_tts_voice_from_extensions,
    extract_tts_voice_from_character,
)


def card_from_character(character: Character) -> CharacterCard:
    profile = character.profile or {}
    meta = character.metadata or {}
    stored = meta.get("card")
    if isinstance(stored, dict) and stored.get("spec") in ("chara_card_v2", "chara_card_v3"):
        card = CharacterCard.from_v2_dict(stored)
        if not card.name:
            card.name = character.name
        tts_voice = extract_tts_voice_from_character(character)
        if tts_voice:
            card.extensions = dict(card.extensions or {})
            card.extensions["tts_voice"] = tts_voice
        return card

    tts_voice = extract_tts_voice_from_character(character)
    extensions = {}
    if isinstance(stored, dict):
        data = stored.get("data") if isinstance(stored.get("data"), dict) else stored
        if isinstance(data, dict) and isinstance(data.get("extensions"), dict):
            extensions = dict(data["extensions"])
    if tts_voice:
        extensions["tts_voice"] = tts_voice

    return CharacterCard(
        name=character.name,
        description=str(profile.get("description", profile.get("summary", ""))).strip(),
        personality=str(profile.get("personality", "")).strip(),
        scenario=str(profile.get("scenario", "")).strip(),
        first_mes=str(profile.get("first_mes", "")).strip(),
        mes_example=str(profile.get("mes_example", "")).strip(),
        system_prompt=str(profile.get("system_prompt", "")).strip()
        if profile.get("system_prompt")
        else str((meta.get("card") or {}).get("data", {}).get("system_prompt", ""))
        if isinstance(meta.get("card"), dict)
        else "",
        post_history_instructions=str(profile.get("post_history_instructions", "")).strip(),
        alternate_greetings=list(profile.get("alternate_greetings") or [])
        if isinstance(profile.get("alternate_greetings"), list)
        else [],
        extensions=extensions,
    )


def apply_card_to_character(character: Character, card: CharacterCard) -> Character:
    profile = dict(character.profile or {})
    metadata = dict(character.metadata or {})

    profile.update(
        {
            "summary": card.description or profile.get("summary", ""),
            "description": card.description,
            "personality": card.personality,
            "scenario": card.scenario,
            "first_mes": card.first_mes,
            "mes_example": card.mes_example,
            "system_prompt": card.system_prompt,
            "post_history_instructions": card.post_history_instructions,
            "alternate_greetings": list(card.alternate_greetings),
            "group_only_greetings": list(card.group_only_greetings),
        }
    )
    voice = extract_tts_voice_from_extensions(card.extensions)
    if voice:
        metadata["tts_voice"] = voice
    elif not metadata.get("tts_voice"):
        metadata["tts_voice"] = extract_tts_voice_from_character(character)

    metadata["card"] = card.to_export_dict(prefer_v3=card.card_spec == "chara_card_v3")
    if metadata.get("tts_voice"):
        card_data = metadata["card"]
        if isinstance(card_data, dict):
            inner = card_data.get("data") if isinstance(card_data.get("data"), dict) else card_data
            if isinstance(inner, dict):
                ext = dict(inner.get("extensions") or {})
                ext["tts_voice"] = metadata["tts_voice"]
                inner["extensions"] = ext
                if "data" in card_data:
                    card_data["data"] = inner

    character.name = card.name or character.name
    character.profile = profile
    character.metadata = metadata
    return character


def avatar_relpath(world_id: str, character_id: str, ext: str = "png") -> str:
    return f"worlds/{world_id}/characters/{character_id}/avatar.{ext.lstrip('.')}"


def get_avatar_relpath(character: Character) -> str | None:
    path = (character.metadata or {}).get("avatar_path")
    return str(path).strip() if path else None
