from __future__ import annotations

from novel_world.modules.ai.domain.entities import ChatMessage
from novel_world.modules.ai.domain.prompt_layers import AuthorsNote, PromptLayers
from novel_world.modules.ai.services.lore_engine import LoreResult
from novel_world.modules.ai.services.prompt_assembler import PromptAssembler


def test_build_system_block_order() -> None:
    asm = PromptAssembler()
    layers = PromptLayers(main="MAIN", system_extra="EXTRA")
    system = asm.build_system_block(
        ["BASE"],
        layers,
        {"before_main": "LORE"},
        "【需要记住的信息】\n- fact",
    )
    assert system.index("LORE") < system.index("MAIN")
    assert "BASE" in system
    assert "EXTRA" in system
    assert "fact" in system


def test_authors_note_depth() -> None:
    asm = PromptAssembler()
    layers = PromptLayers(authors_note=AuthorsNote(content="Note here", depth=1))
    messages = [
        ChatMessage(role="system", content="sys"),
        ChatMessage(role="user", content="u1"),
        ChatMessage(role="assistant", content="a1"),
        ChatMessage(role="user", content="u2"),
    ]
    out = asm.inject_authors_note(messages, layers)
    assert sum(1 for m in out if "Author's Note" in m.content) == 1
    assert out[-2].role == "system"


def test_lore_before_examples() -> None:
    asm = PromptAssembler()
    lore = LoreResult(before_examples=["Example lore"])
    messages = [ChatMessage(role="system", content="sys")]
    out = asm.apply_lore_to_messages(messages, lore)
    assert len(out) == 2
    assert "示例参考 Lore" in out[1].content


def test_serialize_chatml_template() -> None:
    asm = PromptAssembler()
    messages = [
        ChatMessage(role="system", content="sys block"),
        ChatMessage(role="user", content="hello"),
    ]
    out = asm.serialize_messages(messages, "chatml")
    assert len(out) == 1
    assert out[0]["role"] == "prompt"
    assert "<|im_start|>system" in out[0]["content"]
    assert "<|im_start|>user" in out[0]["content"]


def test_serialize_alpaca_template() -> None:
    asm = PromptAssembler()
    messages = [
        ChatMessage(role="system", content="rules"),
        ChatMessage(role="user", content="hi"),
    ]
    out = asm.serialize_messages(messages, "alpaca")
    assert len(out) == 1
    assert "### System:" in out[0]["content"]
    assert "### User:" in out[0]["content"]
    assert "### Response:" in out[0]["content"]


def test_build_debug_uses_template() -> None:
    asm = PromptAssembler()
    layers = PromptLayers(template="chatml")
    debug = asm.build_debug(
        "sys",
        [ChatMessage(role="user", content="u")],
        LoreResult(),
        [],
        layers,
    )
    assert debug.messages[0]["role"] == "prompt"
