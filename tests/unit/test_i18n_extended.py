from __future__ import annotations

import json
from pathlib import Path

from novel_world.web.i18n import (
    DEFAULT_LOCALE,
    get_js_catalog,
    html_lang,
    list_locales,
    resolve_locale,
    t,
)

I18N_DIR = Path(__file__).resolve().parents[2] / "src" / "novel_world" / "web" / "i18n"


def test_i18n_zh_nav() -> None:
    assert t("nav.chat") == "聊天"
    assert t("nav.settings") == "设置"
    assert t("nav.guide") == "使用指南"


def test_session_labels_chinese() -> None:
    assert t("session.temperature") == "采样温度"
    assert t("session.layer_jailbreak") == "越狱指令层"
    assert "Temperature" not in t("session.temperature")


def test_resolve_locale() -> None:
    assert resolve_locale("zh") == "zh"
    assert resolve_locale("en") == "en"
    assert resolve_locale("invalid") == DEFAULT_LOCALE


def test_list_locales_includes_zh_en() -> None:
    locales = list_locales()
    assert "zh" in locales
    assert "en" in locales


def test_html_lang() -> None:
    assert html_lang("zh") == "zh-CN"
    assert html_lang("en") == "en"


def test_help_keys_exist() -> None:
    assert t("help.session.temperature").startswith("控制")
    assert len(t("help.settings.locale")) > 5


def test_guide_page_keys() -> None:
    assert t("guide_page.title") == "使用指南"
    assert len(t("guide_page.quick_start_body")) > 20


def test_en_catalog_has_nav_guide() -> None:
    catalog = get_js_catalog("en")
    assert catalog.get("nav.guide") == "User Guide"


def test_zh_json_valid() -> None:
    json.loads((I18N_DIR / "zh.json").read_text(encoding="utf-8"))


def test_en_json_valid() -> None:
    json.loads((I18N_DIR / "en.json").read_text(encoding="utf-8"))
