from __future__ import annotations

from pathlib import Path

import pytest

from novel_world.bootstrap.app_context import create_app_context
from novel_world.web.app import _build_provider_options
from novel_world.web.i18n import t


@pytest.fixture
def app_runtime(tmp_path: Path):
    ctx = create_app_context(tmp_path)
    runtime = ctx.open()
    yield runtime
    runtime.close()


def test_i18n_zh_nav() -> None:
    assert t("nav.chat") == "聊天"
    assert t("nav.settings") == "设置"


def test_provider_options_only_configured(app_runtime) -> None:
    provider = app_runtime.providers.create(
        "DeepSeek",
        "openai_compatible",
        {
            "api_key": "k",
            "base_url": "https://api.deepseek.com/v1",
            "model": "deepseek-chat",
            "catalog_slug": "deepseek",
        },
    )
    enabled = app_runtime.providers.list_enabled()
    options = _build_provider_options(enabled)
    assert len(options) == 1
    assert options[0]["value"] == provider.id
    assert all(not str(o["value"]).startswith("preset:") for o in options)
