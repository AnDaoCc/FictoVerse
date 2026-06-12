from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

I18N_DIR = Path(__file__).resolve().parent
DEFAULT_LOCALE = "zh"

LOCALE_LABELS: dict[str, str] = {
    "zh": "简体中文",
    "en": "English",
}


@lru_cache(maxsize=8)
def _load_locale(locale: str) -> dict[str, str]:
    path = I18N_DIR / f"{locale}.json"
    if not path.exists():
        path = I18N_DIR / f"{DEFAULT_LOCALE}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return _flatten(data)


def _flatten(data: dict[str, Any], prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in data.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            out.update(_flatten(value, full_key))
        else:
            out[full_key] = str(value)
    return out


def list_locales() -> list[str]:
    locales: list[str] = []
    for path in sorted(I18N_DIR.glob("*.json")):
        code = path.stem
        if code.startswith("_"):
            continue
        locales.append(code)
    return locales or [DEFAULT_LOCALE]


def locale_label(code: str) -> str:
    return LOCALE_LABELS.get(code, code)


def resolve_locale(code: str | None) -> str:
    value = (code or DEFAULT_LOCALE).strip().lower()
    if value in list_locales():
        return value
    return DEFAULT_LOCALE


def html_lang(locale: str) -> str:
    if locale == "zh":
        return "zh-CN"
    if locale == "en":
        return "en"
    return locale


def t(key: str, locale: str = DEFAULT_LOCALE, **kwargs: Any) -> str:
    catalog = _load_locale(locale)
    text = catalog.get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except KeyError:
            return text
    return text


def get_js_catalog(locale: str = DEFAULT_LOCALE) -> dict[str, str]:
    return dict(_load_locale(locale))
