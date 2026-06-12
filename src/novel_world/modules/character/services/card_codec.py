from __future__ import annotations

import base64
import json
from io import BytesIO
from typing import Any

from PIL import Image, PngImagePlugin

from novel_world.core.exceptions import ValidationError
from novel_world.modules.character.domain.character_card import CARD_SPEC, CARD_SPEC_V3, CharacterCard
from novel_world.modules.character.services.card_v3_codec import normalize_card_warnings

CHARA_PNG_KEY = "chara"


def card_warnings_from_raw(raw: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    spec = str(raw.get("spec", "")).strip()
    if spec == CARD_SPEC_V3:
        warnings.append("已识别为酒馆 V3 角色卡。")
    elif spec and spec not in (CARD_SPEC, CARD_SPEC_V3):
        warnings.append(f"未知的 spec「{spec}」，已按 V2/V3 字段解析。")
    elif not spec:
        if isinstance(raw.get("data"), dict):
            warnings.append("未找到 spec 字段，已按 V2 data 包装解析。")
        else:
            warnings.append("未找到 spec 字段，已按扁平 JSON 解析。")
    data = raw.get("data") if isinstance(raw.get("data"), dict) else raw
    if isinstance(data, dict) and not str(data.get("name", "")).strip():
        warnings.append("角色卡缺少 name 字段。")
    return warnings


def card_from_json_dict(raw: dict[str, Any]) -> tuple[CharacterCard, list[str]]:
    if not isinstance(raw, dict):
        raise ValidationError("角色卡 JSON 必须是对象。")
    warnings = normalize_card_warnings(raw, card_warnings_from_raw(raw))
    card = CharacterCard.from_v2_dict(raw)
    return card, warnings


def card_from_json_bytes(data: bytes) -> CharacterCard:
    card, _ = card_from_json_bytes_with_warnings(data)
    return card


def card_from_json_bytes_with_warnings(data: bytes) -> tuple[CharacterCard, list[str]]:
    try:
        raw = json.loads(data.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValidationError(f"角色卡 JSON 无效：{exc}") from exc
    if isinstance(raw, dict):
        from novel_world.modules.character.services.chub_codec import is_chub_card, parse_chub_card
        from novel_world.modules.character.services.risu_codec import is_risu_card, parse_risu_card

        if is_chub_card(raw):
            return parse_chub_card(raw), ["已识别为 Chub.ai 角色卡格式。"]
        if is_risu_card(raw):
            return parse_risu_card(raw), ["已识别为 RisuAI 角色卡格式。"]
    return card_from_json_dict(raw)


def card_to_json_bytes(card: CharacterCard, *, indent: int = 2) -> bytes:
    return json.dumps(card.to_v2_dict(), ensure_ascii=False, indent=indent).encode("utf-8")


def _extract_chara_text(info: dict[str, Any]) -> str | None:
    for key, value in info.items():
        if str(key).lower() in (CHARA_PNG_KEY, "ccv3") and value:
            return str(value)
    return None


def card_from_png_bytes(data: bytes) -> tuple[CharacterCard, bytes]:
    card, _, png = card_from_png_bytes_with_warnings(data)
    return card, png


def card_from_png_bytes_with_warnings(data: bytes) -> tuple[CharacterCard, list[str], bytes]:
    """从 PNG 提取 V2 卡；返回 (卡片, 警告, 原始 PNG 字节供存头像)。"""
    try:
        img = Image.open(BytesIO(data))
        img.load()
    except Exception as exc:
        raise ValidationError(f"无法读取 PNG 角色卡：{exc}") from exc

    chara_b64 = _extract_chara_text(dict(img.info))
    if not chara_b64:
        raise ValidationError("PNG 中未找到 chara 元数据块（需酒馆 V2 PNG 卡）。")

    try:
        decoded = base64.b64decode(chara_b64)
        raw = json.loads(decoded.decode("utf-8"))
    except Exception as exc:
        raise ValidationError(f"PNG chara 块解析失败：{exc}") from exc

    if not isinstance(raw, dict):
        raise ValidationError("PNG chara 块内容无效。")
    card, warnings = card_from_json_dict(raw)
    return card, warnings, data


def card_to_png_bytes(card: CharacterCard, image_bytes: bytes | None = None) -> bytes:
    """将 V2 JSON 嵌入 PNG chara 块；image_bytes 为空时使用占位图。"""
    payload = base64.b64encode(card_to_json_bytes(card, indent=0)).decode("ascii")
    meta = PngImagePlugin.PngInfo()
    meta.add_text(CHARA_PNG_KEY, payload)

    if image_bytes:
        try:
            img = Image.open(BytesIO(image_bytes)).convert("RGBA")
        except Exception:
            img = _placeholder_avatar(card.name)
    else:
        img = _placeholder_avatar(card.name)

    out = BytesIO()
    img.save(out, format="PNG", pnginfo=meta)
    return out.getvalue()


def _placeholder_avatar(name: str, size: int = 512) -> Image.Image:
    from PIL import ImageDraw, ImageFont

    img = Image.new("RGBA", (size, size), (40, 48, 72, 255))
    draw = ImageDraw.Draw(img)
    letter = (name.strip() or "?")[0].upper()
    try:
        font = ImageFont.truetype("arial.ttf", size // 2)
    except OSError:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), letter, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((size - tw) / 2, (size - th) / 2 - bbox[1]), letter, fill=(200, 210, 240, 255), font=font)
    return img
