"""启动器 API 提供商管理：直连本地数据库，与 Web 设置页能力对齐。"""

from __future__ import annotations

from typing import Any

from novel_world.bootstrap.app_context import create_app_context
from novel_world.core.exceptions import DomainError, ValidationError
from novel_world.launcher.bootstrap import get_root
from novel_world.modules.ai.catalog import catalog_as_dicts, get_preset


def _ok(data: Any = None, message: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {"ok": True}
    if message:
        out["message"] = message
    if data is not None:
        out["data"] = data
    return out


def _err(message: str) -> dict[str, Any]:
    return {"ok": False, "message": message}


def _app_ctx():
    return create_app_context(get_root())


def _mask_api_key(key: str) -> str:
    text = (key or "").strip()
    if not text:
        return ""
    if len(text) <= 4:
        return "***"
    return f"{text[:2]}***{text[-2:]}"


def _provider_dict(provider: Any) -> dict[str, Any]:
    cfg = provider.config if isinstance(provider.config, dict) else {}
    return {
        "id": str(provider.id),
        "name": provider.name,
        "type": provider.type,
        "enabled": bool(provider.enabled),
        "base_url": str(cfg.get("base_url") or ""),
        "model": str(cfg.get("model") or ""),
        "api_key_masked": _mask_api_key(str(cfg.get("api_key") or "")),
        "catalog_slug": str(cfg.get("catalog_slug") or ""),
    }


def list_providers() -> dict[str, Any]:
    ctx = _app_ctx()
    runtime = ctx.open()
    try:
        providers = runtime.providers.list_all()
        return _ok([_provider_dict(p) for p in providers])
    finally:
        runtime.close()


def list_vendor_catalog() -> dict[str, Any]:
    return _ok(catalog_as_dicts())


def create_provider(
    name: str = "",
    provider_type: str = "",
    api_key: str = "",
    base_url: str = "",
    model: str = "",
    preset_slug: str = "",
) -> dict[str, Any]:
    ctx = _app_ctx()
    runtime = ctx.open()
    try:
        preset = get_preset(preset_slug.strip()) if preset_slug.strip() else None
        resolved_name = name.strip() or (preset.name if preset else "")
        resolved_type = provider_type.strip() or (preset.provider_type if preset else "")
        if not resolved_name or not resolved_type:
            raise ValidationError("请选择厂商或填写提供商名称与类型。")
        resolved_base = base_url.strip() or (preset.base_url if preset else "")
        resolved_model = model.strip() or (preset.default_model if preset else "")
        config: dict[str, str] = {
            "api_key": api_key.strip(),
            "base_url": resolved_base,
            "model": resolved_model,
        }
        if preset:
            config["catalog_slug"] = preset.slug
        provider = runtime.providers.create(resolved_name, resolved_type, config)  # type: ignore[arg-type]
        runtime.commit()
        return _ok(_provider_dict(provider), message="已添加提供商")
    except (ValidationError, DomainError) as e:
        runtime.rollback()
        return _err(str(e))
    except Exception as e:
        runtime.rollback()
        return _err(f"添加失败：{e}")
    finally:
        runtime.close()


def delete_provider(provider_id: str) -> dict[str, Any]:
    ctx = _app_ctx()
    runtime = ctx.open()
    try:
        removed_sessions = runtime.chat.delete_sessions_by_provider(provider_id)
        runtime.providers.delete(provider_id)
        runtime.commit()
        if removed_sessions:
            return _ok(message=f"已删除提供商，并清理了 {removed_sessions} 个关联对话。")
        return _ok(message="已删除提供商。")
    except (ValidationError, DomainError) as e:
        runtime.rollback()
        return _err(str(e))
    except Exception as e:
        runtime.rollback()
        return _err(f"删除失败：{e}")
    finally:
        runtime.close()


def test_provider(provider_id: str, model: str = "") -> dict[str, Any]:
    ctx = _app_ctx()
    runtime = ctx.open()
    try:
        reply = runtime.providers.test_connection(provider_id, model=model.strip() or None)
        runtime.commit()
        return _ok({"reply": reply[:200]}, message=f"连接成功：{reply[:80]}")
    except (ValidationError, DomainError) as e:
        runtime.rollback()
        return _err(str(e))
    except Exception as e:
        runtime.rollback()
        return _err(str(e))
    finally:
        runtime.close()
