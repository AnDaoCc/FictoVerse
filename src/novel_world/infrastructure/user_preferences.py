from __future__ import annotations

import json
import sqlite3
from typing import Any

PREFS_KEY = "user_prefs"
DEFAULT_PREFS: dict[str, Any] = {
    "locale": "zh",
    "show_thinking": False,
    "tts_enabled": False,
    "tts_auto_play": False,
    "tts_rate": 1.0,
    "tts_voice": "",
    "tts_backend": "edge",
    "tts_openai_voice": "alloy",
    "tts_openai_api_key": "",
    "tts_openai_base_url": "https://api.openai.com/v1",
    "tts_openai_model": "tts-1",
    "tts_openai_auth_style": "bearer",
    "tts_openai_voices_json": "",
    "tts_custom": {},
    "disabled_extensions": [],
    "default_generation": {
        "temperature": 0.8,
        "top_p": 1.0,
        "max_tokens": 512,
        "repetition_penalty": 1.0,
        "stop": [],
    },
    "default_prompt_layers": {},
    "default_prompt_profile": {},
    "global_regex_scripts": [],
    "global_stscripts": [],
    "stscript_global_vars": {},
    "card_export_spec": "v3",
    "lore_token_budget": 2000,
    "embedding_provider": "hash",
    "embedding_model": "text-embedding-3-small",
    "embedding_base_url": "",
    "embedding_api_key": "",
    "vector_dimension": 128,
    "vector_min_score": 0.2,
    "chunk_size": 500,
    "sd_webui_url": "http://127.0.0.1:7860",
}


def get_user_prefs(conn: sqlite3.Connection) -> dict[str, Any]:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (PREFS_KEY,)).fetchone()
    if row is None:
        return dict(DEFAULT_PREFS)
    try:
        data = json.loads(row["value"])
    except (json.JSONDecodeError, TypeError):
        return dict(DEFAULT_PREFS)
    merged = dict(DEFAULT_PREFS)
    if isinstance(data, dict):
        merged.update(data)
    return merged


def save_user_prefs(conn: sqlite3.Connection, prefs: dict[str, Any]) -> dict[str, Any]:
    merged = dict(DEFAULT_PREFS)
    merged.update(prefs)
    conn.execute(
        """
        INSERT INTO meta (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (PREFS_KEY, json.dumps(merged, ensure_ascii=False)),
    )
    return merged
