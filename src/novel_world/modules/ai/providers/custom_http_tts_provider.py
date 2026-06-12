from __future__ import annotations

import base64
import json
import re
from typing import Any

import httpx

from novel_world.modules.ai.services.tts_voice_resolver import strip_text_for_tts

_DEFAULT_VOICES = [{"id": "default", "name": "默认", "locale": "", "gender": ""}]


def _is_allowed_url(url: str) -> bool:
    u = (url or "").strip().lower()
    return u.startswith("http://") or u.startswith("https://")


def _json_path_get(data: Any, path: str) -> Any:
    cur = data
    for part in (path or "").split("."):
        part = part.strip()
        if not part:
            continue
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list) and part.isdigit():
            idx = int(part)
            cur = cur[idx] if 0 <= idx < len(cur) else None
        else:
            return None
    return cur


def apply_body_template(template: str, *, text: str, voice: str, rate: float) -> str:
    body = template or "{}"
    safe_text = json.dumps(text, ensure_ascii=False)[1:-1]
    body = body.replace("{{text}}", safe_text)
    body = body.replace("{{voice}}", voice or "default")
    body = body.replace("{{rate}}", str(rate))
    return body


def normalize_custom_config(cfg: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(cfg or {})
    return {
        "url": str(raw.get("url") or "").strip(),
        "method": str(raw.get("method") or "POST").upper(),
        "headers": dict(raw.get("headers") or {}) if isinstance(raw.get("headers"), dict) else {},
        "body_template": str(raw.get("body_template") or '{"text":"{{text}}","voice":"{{voice}}"}'),
        "response_mode": str(raw.get("response_mode") or "binary").lower(),
        "response_json_path": str(raw.get("response_json_path") or "").strip(),
        "media_type": str(raw.get("media_type") or "audio/mpeg"),
        "voices": list(raw.get("voices") or []) if isinstance(raw.get("voices"), list) else [],
        "voices_url": str(raw.get("voices_url") or "").strip(),
    }


class CustomHttpTTSProvider:
    """自定义 HTTP TTS：用户配置 URL、请求体模板与响应解析。"""

    def __init__(self, config: dict[str, Any]) -> None:
        self._cfg = normalize_custom_config(config)

    def media_type(self) -> str:
        return self._cfg.get("media_type") or "audio/mpeg"

    def list_voices(self, *, locale_prefix: str = "") -> list[dict[str, str]]:
        voices = self._cfg.get("voices") or []
        parsed: list[dict[str, str]] = []
        for item in voices:
            if not isinstance(item, dict):
                continue
            vid = str(item.get("id") or item.get("voice") or "").strip()
            if not vid:
                continue
            parsed.append(
                {
                    "id": vid,
                    "name": str(item.get("name") or vid),
                    "locale": str(item.get("locale") or ""),
                    "gender": str(item.get("gender") or ""),
                }
            )
        if parsed:
            if locale_prefix:
                prefix = locale_prefix.lower()
                filtered = [v for v in parsed if v.get("locale", "").lower().startswith(prefix)]
                return filtered or parsed
            return parsed

        voices_url = self._cfg.get("voices_url") or ""
        if voices_url and _is_allowed_url(voices_url):
            try:
                with httpx.Client(timeout=30.0) as client:
                    resp = client.get(voices_url)
                    resp.raise_for_status()
                    data = resp.json()
                items = data if isinstance(data, list) else data.get("voices", []) if isinstance(data, dict) else []
                if isinstance(items, list):
                    for item in items:
                        if not isinstance(item, dict):
                            continue
                        vid = str(item.get("id") or item.get("voice") or "").strip()
                        if vid:
                            parsed.append(
                                {
                                    "id": vid,
                                    "name": str(item.get("name") or vid),
                                    "locale": str(item.get("locale") or ""),
                                    "gender": str(item.get("gender") or ""),
                                }
                            )
            except Exception:
                pass
        return parsed or list(_DEFAULT_VOICES)

    def synthesize(self, text: str, *, voice: str = "", rate: float = 1.0) -> bytes:
        cleaned = strip_text_for_tts(text)
        if not cleaned:
            return b""
        url = self._cfg.get("url") or ""
        if not _is_allowed_url(url):
            return b""

        body_str = apply_body_template(
            self._cfg.get("body_template") or "",
            text=cleaned,
            voice=voice or "default",
            rate=rate,
        )
        headers = dict(self._cfg.get("headers") or {})
        method = self._cfg.get("method") or "POST"

        with httpx.Client(timeout=120.0) as client:
            req_kwargs: dict[str, Any] = {"headers": headers}
            if method in ("GET", "DELETE"):
                resp = client.request(method, url, **req_kwargs)
            else:
                content_type = str(headers.get("Content-Type") or headers.get("content-type") or "")
                if "application/json" in content_type.lower() or body_str.strip().startswith("{"):
                    try:
                        req_kwargs["json"] = json.loads(body_str)
                    except json.JSONDecodeError:
                        req_kwargs["content"] = body_str.encode("utf-8")
                        headers.setdefault("Content-Type", "application/json")
                else:
                    req_kwargs["content"] = body_str.encode("utf-8")
                resp = client.request(method, url, **req_kwargs)
            resp.raise_for_status()
            return self._parse_response(client, resp)

    def _parse_response(self, client: httpx.Client, resp: httpx.Response) -> bytes:
        mode = self._cfg.get("response_mode") or "binary"
        if mode == "binary":
            ctype = resp.headers.get("content-type", "")
            if "application/json" in ctype.lower():
                return self._parse_json_payload(resp.json())
            return resp.content
        if mode == "json_base64":
            return self._parse_json_payload(resp.json())
        if mode == "json_url":
            data = resp.json()
            path = self._cfg.get("response_json_path") or "url"
            audio_url = _json_path_get(data, path)
            if isinstance(audio_url, str) and _is_allowed_url(audio_url):
                dl = client.get(audio_url)
                dl.raise_for_status()
                return dl.content
        return b""

    def _parse_json_payload(self, data: Any) -> bytes:
        path = self._cfg.get("response_json_path") or "audio"
        raw = _json_path_get(data, path)
        if raw is None and isinstance(data, dict):
            raw = data.get("audio") or data.get("data")
        if isinstance(raw, bytes):
            return raw
        if isinstance(raw, str):
            s = raw.strip()
            if s.startswith("data:") and "," in s:
                s = s.split(",", 1)[1]
            s = re.sub(r"\s+", "", s)
            try:
                return base64.b64decode(s, validate=False)
            except Exception:
                return b""
        return b""
