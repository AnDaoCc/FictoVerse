from __future__ import annotations

from novel_world.modules.ai.catalog import VENDOR_CATALOG, get_preset


def test_vendor_catalog_has_major_providers() -> None:
    slugs = {item.slug for item in VENDOR_CATALOG}
    assert "openai" in slugs
    assert "anthropic" in slugs
    assert "gemini" in slugs
    assert "deepseek" in slugs
    assert "ollama" in slugs


def test_get_preset_returns_vendor() -> None:
    preset = get_preset("openai")
    assert preset is not None
    assert preset.provider_type == "openai"
    assert preset.default_model == "gpt-4o-mini"


def test_deepseek_preset_uses_v4_models() -> None:
    preset = get_preset("deepseek")
    assert preset is not None
    assert preset.default_model == "deepseek-v4-flash"
    assert "deepseek-v4-pro" in preset.models
