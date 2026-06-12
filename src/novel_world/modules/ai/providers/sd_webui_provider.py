from __future__ import annotations

import base64
from typing import Any

import httpx


class SDWebUIProvider:
    def __init__(self, *, base_url: str = "http://127.0.0.1:7860") -> None:
        self._base_url = base_url.rstrip("/")

    def txt2img(self, prompt: str, *, negative_prompt: str = "", width: int = 512, height: int = 512, steps: int = 20) -> bytes:
        payload: dict[str, Any] = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "width": width,
            "height": height,
            "steps": steps,
        }
        with httpx.Client(timeout=300.0) as client:
            resp = client.post(f"{self._base_url}/sdapi/v1/txt2img", json=payload)
            resp.raise_for_status()
            data = resp.json()
        images = data.get("images") or []
        if not images:
            return b""
        return base64.b64decode(images[0])
