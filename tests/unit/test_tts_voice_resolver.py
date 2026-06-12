from dataclasses import dataclass, field
from typing import Any

from novel_world.modules.ai.services.tts_voice_resolver import (
    DEFAULT_EDGE_VOICE,
    extract_tts_voice_from_extensions,
    resolve_voice_for_character,
    resolve_voice_for_speaker,
    strip_text_for_tts,
)
from novel_world.modules.character.domain.character_card import CharacterCard
from novel_world.modules.character.services.card_mapper import apply_card_to_character


@dataclass
class FakeCharacter:
    id: str = "c1"
    name: str = "Test"
    profile: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


def test_extract_extensions_tts_voice() -> None:
    assert extract_tts_voice_from_extensions({"tts_voice": "zh-CN-YunxiNeural"}) == "zh-CN-YunxiNeural"
    assert extract_tts_voice_from_extensions({"edge_tts_voice": "zh-CN-XiaoyiNeural"}) == "zh-CN-XiaoyiNeural"


def test_resolve_character_metadata_priority() -> None:
    ch = FakeCharacter(metadata={"tts_voice": "zh-CN-YunyangNeural"})
    assert resolve_voice_for_character(ch) == "zh-CN-YunyangNeural"


def test_resolve_speaker_and_global_fallback() -> None:
    ch = FakeCharacter(id="c9", metadata={"tts_voice": "zh-CN-XiaohanNeural"})
    speaker = {"character_id": "c9", "tts_voice": "zh-CN-YunxiNeural"}
    assert (
        resolve_voice_for_speaker(speaker, characters_by_id={"c9": ch}, global_default="")
        == "zh-CN-YunxiNeural"
    )
    assert resolve_voice_for_speaker(None, global_default="") == DEFAULT_EDGE_VOICE


def test_strip_text_for_tts() -> None:
    assert strip_text_for_tts("**你好** `世界`") == "你好 世界"


def test_card_apply_roundtrip_tts_voice() -> None:
    ch = FakeCharacter()
    card = CharacterCard(name="A", extensions={"tts_voice": "zh-CN-XiaoxiaoNeural"})
    apply_card_to_character(ch, card)
    assert ch.metadata.get("tts_voice") == "zh-CN-XiaoxiaoNeural"
    exported = ch.metadata["card"]
    inner = exported.get("data", exported)
    assert inner["extensions"]["tts_voice"] == "zh-CN-XiaoxiaoNeural"
