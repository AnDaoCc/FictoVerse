from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request as StarletteRequest

from novel_world.application.use_cases.create_world import CreateWorldUseCase
from novel_world.bootstrap.app_context import create_app_context
from novel_world.bootstrap.app_factory import create_app
from novel_world.bootstrap.config import project_root
from novel_world.core.domain.ids import CharacterId, SaveId, WorldId
from novel_world.core.exceptions import DomainError, ValidationError
from novel_world.bootstrap.config import default_config
from novel_world.infrastructure.server_meta import read_server_meta, remove_server_meta, write_server_meta
from novel_world.modules.ai.catalog import VENDOR_CATALOG, catalog_as_dicts, get_preset
from novel_world.modules.documents.services.document_extractor import extract_text_from_bytes
from novel_world.infrastructure.user_preferences import get_user_prefs, save_user_prefs
from novel_world.infrastructure.repositories.sqlite_repositories import SqliteCharacterRepository
from novel_world.modules.character.services.card_mapper import get_avatar_relpath
from novel_world.modules.character.services.character_card_service import CharacterCardService
from novel_world.modules.extensions.hook_bus import run_hooks
from novel_world.modules.extensions.hook_catalog import hook_catalog_for_ui
from novel_world.modules.extensions.mod_registry import (
    get_enabled_frontend_assets,
    install_mod_zip,
    resolve_mod_asset_path,
    uninstall_mod,
)
from novel_world.modules.ai.services.user_persona import (
    display_name,
    merge_session_persona,
    persona_from_world_settings,
    store_persona,
)
from novel_world.modules.ai.services.world_speaker import resolve_message_speaker
from novel_world.modules.character.character_roles import (
    normalize_role,
    role_label,
    role_options_for_template,
)
from novel_world.web.credits import AUTHOR_CREDIT_LINE
from novel_world.web.i18n import get_js_catalog, html_lang, list_locales, resolve_locale, t

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = project_root()
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.globals["t"] = t
templates.env.globals["role_label"] = role_label
templates.env.globals["character_role_options"] = role_options_for_template
templates.env.globals["resolve_message_speaker"] = resolve_message_speaker
def _display_transform(text: str, session_id: str = "") -> str:
    from novel_world.infrastructure.user_preferences import get_user_prefs
    from novel_world.modules.ai.services.regex_engine import RegexEngine

    runtime = _ctx().open()
    try:
        prefs = get_user_prefs(runtime.session.connection)
        session_config: dict = {}
        if session_id:
            try:
                session = runtime.chat.get_session(session_id)
                session_config = session.config or {}
            except Exception:
                pass
        regex = RegexEngine.from_prefs_and_session(prefs, session_config)
        out = regex.apply_display(text or "")
        return run_hooks("display.transform", out, session_id=session_id)
    finally:
        runtime.close()


templates.env.globals["display_transform"] = _display_transform

app = FastAPI(title="FictoVerse", version="2026.2.0")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.on_event("startup")
async def _register_server_meta() -> None:
    """Uvicorn 绑定端口后再写入 server.json，避免启动器过早探测失败。"""
    port_raw = os.environ.get("NOVEL_WORLD_SERVER_PORT", "").strip()
    if not port_raw.isdigit():
        return
    host = os.environ.get("NOVEL_WORLD_SERVER_HOST", "127.0.0.1").strip() or "127.0.0.1"
    write_server_meta(
        default_config(PROJECT_ROOT).data_dir,
        host=host,
        port=int(port_raw),
    )


@app.get("/api/health")
def api_health() -> dict[str, bool]:
    return {"ok": True}


_CTX: Any = None


def _ctx(base_dir: Path | None = None):
    if _CTX is not None:
        return _CTX
    return create_app_context(base_dir or PROJECT_ROOT)


def _world_app(base_dir: Path | None = None):
    return create_app(base_dir or PROJECT_ROOT)


def _user_persona_nav(session=None, world=None) -> dict[str, Any]:
    world_settings = None
    if world is not None:
        world_settings = world.settings if isinstance(getattr(world, "settings", None), dict) else {}
    persona = merge_session_persona(
        session.config if session else None,
        world_settings,
    )
    return {
        "user_persona": persona,
        "user_display_name": display_name(persona),
    }


def _character_card_service(world_id: str):
    app_factory = _world_app()
    rt = app_factory.open_world(WorldId(world_id))
    svc = CharacterCardService(
        app_factory.config,
        SqliteCharacterRepository(rt.session.connection),
    )
    return app_factory, rt, svc


def _data_dir_from_form(value: str | None) -> Path | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    return Path(value)


def _json_loads_maybe(text: str, *, default: Any) -> Any:
    text = (text or "").strip()
    if not text:
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ValidationError(f"JSON 格式不正确：{e.msg}") from e


def _normalize_relationships(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    cleaned: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        target = str(item.get("target", "")).strip()
        if not target:
            continue
        cleaned.append(
            {
                "target": target,
                "type": str(item.get("type", "")).strip(),
                "note": str(item.get("note", "")).strip(),
            }
        )
    return cleaned


def _is_localhost(request: StarletteRequest) -> bool:
    client = request.client
    return client is not None and client.host in {"127.0.0.1", "::1", "localhost"}


def _world_spine_hue(world_id: str) -> int:
    return sum(ord(c) for c in world_id) % 360


def _list_worlds(base_dir: Path | None = None) -> list[dict[str, Any]]:
    app_factory = create_app(base_dir or PROJECT_ROOT)
    worlds: list[dict[str, Any]] = []
    for wid in app_factory.list_world_ids():
        rt = app_factory.open_world(wid)
        try:
            w = rt.world.get(wid)
            desc = (w.description or "").strip()
            preview = desc[:60] + ("…" if len(desc) > 60 else "")
            cover_url = _world_background_url(str(w.id))
            worlds.append(
                {
                    "id": str(w.id),
                    "name": w.name,
                    "genre": w.genre or "",
                    "description_preview": preview,
                    "spine_hue": _world_spine_hue(str(w.id)),
                    "cover_url": cover_url,
                }
            )
        except DomainError:
            wid_str = str(wid)
            worlds.append(
                {
                    "id": wid_str,
                    "name": f"(损坏/空世界) {wid_str}",
                    "genre": "",
                    "description_preview": "",
                    "spine_hue": _world_spine_hue(wid_str),
                    "cover_url": "",
                }
            )
        finally:
            rt.close()
    return worlds


def _list_worlds_with_characters(base_dir: Path | None = None) -> list[dict[str, Any]]:
    app_factory = create_app(base_dir or PROJECT_ROOT)
    out: list[dict[str, Any]] = []
    for wid in app_factory.list_world_ids():
        rt = app_factory.open_world(wid)
        try:
            w = rt.world.get(wid)
            chars = rt.character.list_by_world(wid, active_only=False)
            out.append(
                {
                    "id": str(w.id),
                    "name": w.name,
                    "characters": [
                        {"id": str(c.id), "name": c.name, "role": c.role} for c in chars
                    ],
                }
            )
        except DomainError:
            continue
        finally:
            rt.close()
    return out


def _read_user_prefs() -> dict[str, Any]:
    runtime = _ctx().open()
    try:
        return get_user_prefs(runtime.session.connection)
    finally:
        runtime.close()


def _session_background_url(runtime, session) -> str:
    if session is None:
        return ""
    cfg = session.config or {}
    rel = str(cfg.get("background") or "").strip()
    if rel and runtime.background.resolve_path(rel):
        return runtime.background.public_url(rel)
    world_id = str(session.world_id or "").strip()
    if world_id:
        try:
            wrt = _world_app().open_world(WorldId(world_id))
            try:
                world = wrt.world.get(WorldId(world_id))
                settings = world.settings if isinstance(world.settings, dict) else {}
                wrel = str(settings.get("background") or "").strip()
                if wrel and runtime.background.resolve_path(wrel):
                    return runtime.background.public_url(wrel)
            finally:
                wrt.close()
        except DomainError:
            pass
    return ""


def _world_background_url(world_id: str) -> str:
    ctx = _ctx()
    runtime = ctx.open()
    try:
        settings: dict = {}
        try:
            wrt = _world_app().open_world(WorldId(world_id))
            try:
                world = wrt.world.get(WorldId(world_id))
                settings = world.settings if isinstance(world.settings, dict) else {}
            finally:
                wrt.close()
        except DomainError:
            return ""
        wrel = str(settings.get("background") or "").strip()
        if wrel and runtime.background.resolve_path(wrel):
            return runtime.background.public_url(wrel)
    finally:
        runtime.close()
    return ""


def _session_page_extras(runtime, session) -> dict[str, Any]:
    cfg = (session.config or {}) if session else {}
    scripts = cfg.get("display_scripts") or []
    if not isinstance(scripts, list):
        scripts = []
    muted = cfg.get("muted") or []
    if not isinstance(muted, list):
        muted = []
    return {
        "session_background_url": _session_background_url(runtime, session),
        "display_scripts": scripts,
        "muted_member_ids": muted,
    }


def _session_service(runtime, session):
    if session.session_type == "roleplay":
        return runtime.roleplay
    if session.session_type == "group":
        return runtime.group_chat
    return runtime.chat


def _preview_prompt(runtime, session_id: str, content: str = "") -> dict[str, Any]:
    session = runtime.chat.get_session(session_id)
    svc = _session_service(runtime, session)
    return svc.preview_prompt(session_id, content)


def _update_session_config(runtime, session_id: str, patch: dict[str, Any]):
    session = runtime.chat.get_session(session_id)
    svc = _session_service(runtime, session)
    return svc.update_session_config(session_id, patch)


def _parse_keys_field(raw: str) -> list[str]:
    if not raw.strip():
        return []
    parts = [p.strip() for p in raw.replace("，", ",").split(",")]
    return [p for p in parts if p]


def _lore_advanced_from_form(
    *,
    probability: str = "1",
    lore_group: str = "",
    group_override: str = "",
    group_weight: str = "0",
    cooldown: str = "0",
    sticky: str = "0",
    character_filter: str = "",
    filter_type: str = "include",
    scan_depth: str = "0",
    use_group_scoring: str = "",
) -> dict[str, Any]:
    return {
        "probability": float(probability or 1),
        "lore_group": lore_group.strip(),
        "group_override": bool(group_override),
        "group_weight": int(group_weight or 0),
        "cooldown": int(cooldown or 0),
        "sticky": int(sticky or 0),
        "character_filter": _parse_keys_field(character_filter),
        "filter_type": filter_type if filter_type in ("include", "exclude") else "include",
        "scan_depth": int(scan_depth or 0),
        "use_group_scoring": bool(use_group_scoring),
    }


def _lore_entry_from_form(
    *,
    scope: str,
    character_id: str,
    keys: str,
    content: str,
    constant: str,
    selective: str,
    recursive: str,
    priority: str,
    insertion_order: str,
    position: str,
    depth: str,
    enabled: str,
    comment: str,
    entry_id: str = "",
    probability: str = "1",
    lore_group: str = "",
    group_override: str = "",
    group_weight: str = "0",
    cooldown: str = "0",
    sticky: str = "0",
    character_filter: str = "",
    filter_type: str = "include",
    scan_depth: str = "0",
    use_group_scoring: str = "",
):
    from novel_world.infrastructure.repositories.sqlite_lore_repository import new_lore_entry

    if entry_id:
        return None
    advanced = _lore_advanced_from_form(
        probability=probability,
        lore_group=lore_group,
        group_override=group_override,
        group_weight=group_weight,
        cooldown=cooldown,
        sticky=sticky,
        character_filter=character_filter,
        filter_type=filter_type,
        scan_depth=scan_depth,
        use_group_scoring=use_group_scoring,
    )
    return new_lore_entry(
        scope=scope if scope in ("world", "character") else "world",
        character_id=character_id.strip(),
        keys=_parse_keys_field(keys),
        content=content.strip(),
        constant=bool(constant),
        selective=selective != "0",
        recursive=bool(recursive),
        priority=int(priority or 0),
        insertion_order=int(insertion_order or 0),
        position=position or "before_main",
        depth=int(depth or 4),
        enabled=enabled != "0",
        comment=comment.strip(),
        source="manual",
        **advanced,
    )

def _read_mod_assets() -> tuple[list[dict[str, Any]], str]:
    runtime = _ctx().open()
    try:
        prefs = get_user_prefs(runtime.session.connection)
        assets = get_enabled_frontend_assets(
            runtime.extensions,
            disabled=list(prefs.get("disabled_extensions") or []),
        )
        return assets, str(runtime.config.mods_dir)
    finally:
        runtime.close()


def _nav_context(request: Request, *, active: str, world_name: str = "") -> dict[str, Any]:
    prefs = _read_user_prefs()
    locale = resolve_locale(prefs.get("locale"))
    mod_assets, mods_dir = _read_mod_assets()

    def tl(key: str, **kwargs: Any) -> str:
        return t(key, locale, **kwargs)

    return {
        "request": request,
        "active_nav": active,
        "world_name": world_name,
        "data_dir": "",
        "locale": locale,
        "html_lang": html_lang(locale),
        "available_locales": list_locales(),
        "i18n_js": get_js_catalog(locale),
        "user_prefs": prefs,
        "enabled_mod_assets": mod_assets,
        "mods_dir": mods_dir,
        "t": tl,
    }


def _build_provider_options(providers: list) -> list[dict[str, Any]]:
    configured_by_slug: dict[str, Any] = {}
    custom: list[Any] = []
    for provider in providers:
        slug = provider.config.get("catalog_slug")
        if slug:
            configured_by_slug[slug] = provider
        else:
            custom.append(provider)

    options: list[dict[str, Any]] = []
    for preset in VENDOR_CATALOG:
        bound = configured_by_slug.pop(preset.slug, None)
        if bound is not None:
            options.append(
                {
                    "value": bound.id,
                    "label": bound.name or preset.name,
                    "group": bound.name or preset.vendor,
                    "configured": True,
                    "default_model": bound.config.get("model") or preset.default_model,
                    "models": list(preset.models),
                    "slug": preset.slug,
                }
            )

    for provider in custom:
        options.append(
            {
                "value": provider.id,
                "label": provider.name,
                "group": "自定义",
                "configured": True,
                "default_model": provider.config.get("model", ""),
                "models": [provider.config.get("model", "")] if provider.config.get("model") else [],
                "slug": "",
            }
        )
    return options


def _build_provider_option_groups(providers: list) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    current_group = ""
    for option in _build_provider_options(providers):
        if option["group"] != current_group:
            current_group = option["group"]
            groups.append({"label": current_group, "options": []})
        groups[-1]["options"].append(option)
    return groups


def _catalog_with_status(providers: list) -> list[dict[str, Any]]:
    configured_slugs = {
        p.config.get("catalog_slug")
        for p in providers
        if p.config.get("catalog_slug")
    }
    rows: list[dict[str, Any]] = []
    for item in catalog_as_dicts():
        row = dict(item)
        row["configured"] = item["slug"] in configured_slugs
        rows.append(row)
    return rows


@app.get("/", response_class=HTMLResponse)
def home() -> RedirectResponse:
    return RedirectResponse(url="/chat", status_code=302)


# ---------- Settings & Server ----------


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, preset: str | None = None) -> HTMLResponse:
    ctx = _ctx()
    runtime = ctx.open()

    try:
        providers = runtime.providers.list_all()
        server = read_server_meta(runtime.config.data_dir)
        extensions = runtime.extensions
        mods_dir = str(runtime.config.mods_dir)
    finally:
        runtime.close()
    nav = _nav_context(request, active="settings")
    nav["providers"] = providers
    nav["server"] = server
    nav["catalog"] = _catalog_with_status(providers)
    nav["active_preset"] = preset or ""
    nav["extensions"] = extensions
    nav["mods"] = extensions
    nav["hook_catalog"] = hook_catalog_for_ui()
    nav["mods_dir"] = mods_dir
    nav["author_credit_line"] = AUTHOR_CREDIT_LINE
    return templates.TemplateResponse(request, "settings.html", nav)


@app.post("/settings/preferences")
def update_preferences(
    show_thinking: str = Form(default=""),
    tts_enabled: str = Form(default=""),
    tts_auto_play: str = Form(default=""),
    tts_backend: str = Form(default=""),
    tts_rate: str = Form(default="1.0"),
    tts_voice: str = Form(default=""),
    tts_openai_voice: str = Form(default=""),
    tts_openai_api_key: str = Form(default=""),
    tts_openai_base_url: str = Form(default=""),
    tts_openai_model: str = Form(default=""),
    tts_openai_auth_style: str = Form(default=""),
    tts_openai_voices_json: str = Form(default=""),
    tts_custom_url: str = Form(default=""),
    tts_custom_method: str = Form(default=""),
    tts_custom_headers: str = Form(default=""),
    tts_custom_body_template: str = Form(default=""),
    tts_custom_response_mode: str = Form(default=""),
    tts_custom_response_json_path: str = Form(default=""),
    tts_custom_media_type: str = Form(default=""),
    tts_custom_voices_json: str = Form(default=""),
    tts_custom_voices_url: str = Form(default=""),
    locale: str = Form(default=""),
    disabled_extensions: str = Form(default=""),
    embedding_provider: str = Form(default=""),
    sd_webui_url: str = Form(default=""),
) -> RedirectResponse:
    runtime = _ctx().open()
    try:
        existing = get_user_prefs(runtime.session.connection)
        disabled = [
            x.strip()
            for x in (disabled_extensions or "").split(",")
            if x.strip()
        ]
        if not disabled and isinstance(existing.get("disabled_extensions"), list):
            disabled = list(existing.get("disabled_extensions") or [])
        try:
            rate = float(str(tts_rate or "1").strip() or "1")
        except ValueError:
            rate = 1.0
        voices_json_raw = (tts_openai_voices_json or existing.get("tts_openai_voices_json") or "").strip()
        if voices_json_raw:
            try:
                json.loads(voices_json_raw)
            except json.JSONDecodeError:
                voices_json_raw = str(existing.get("tts_openai_voices_json") or "")
        custom_voices_raw = (tts_custom_voices_json or "").strip()
        custom_voices: list[dict[str, str]] = []
        if custom_voices_raw:
            try:
                parsed_voices = json.loads(custom_voices_raw)
                if isinstance(parsed_voices, list):
                    custom_voices = parsed_voices
            except json.JSONDecodeError:
                custom_voices = list((existing.get("tts_custom") or {}).get("voices") or [])
        elif isinstance(existing.get("tts_custom"), dict):
            custom_voices = list(existing.get("tts_custom", {}).get("voices") or [])
        custom_headers: dict[str, str] = {}
        headers_raw = (tts_custom_headers or "").strip()
        if headers_raw:
            try:
                parsed_headers = json.loads(headers_raw)
                if isinstance(parsed_headers, dict):
                    custom_headers = {str(k): str(v) for k, v in parsed_headers.items()}
            except json.JSONDecodeError:
                custom_headers = dict((existing.get("tts_custom") or {}).get("headers") or {})
        elif isinstance(existing.get("tts_custom"), dict):
            custom_headers = dict(existing.get("tts_custom", {}).get("headers") or {})
        prev_custom = existing.get("tts_custom") if isinstance(existing.get("tts_custom"), dict) else {}
        tts_custom = {
            "url": (tts_custom_url or prev_custom.get("url") or "").strip(),
            "method": (tts_custom_method or prev_custom.get("method") or "POST").strip().upper(),
            "headers": custom_headers,
            "body_template": (
                tts_custom_body_template
                or prev_custom.get("body_template")
                or '{"text":"{{text}}","voice":"{{voice}}"}'
            ),
            "response_mode": (tts_custom_response_mode or prev_custom.get("response_mode") or "binary").strip().lower(),
            "response_json_path": (tts_custom_response_json_path or prev_custom.get("response_json_path") or "").strip(),
            "media_type": (tts_custom_media_type or prev_custom.get("media_type") or "audio/mpeg").strip(),
            "voices": custom_voices,
            "voices_url": (tts_custom_voices_url or prev_custom.get("voices_url") or "").strip(),
        }
        save_user_prefs(
            runtime.session.connection,
            {
                **existing,
                "show_thinking": show_thinking.strip().lower() in ("1", "true", "on", "yes"),
                "tts_enabled": tts_enabled.strip().lower() in ("1", "true", "on", "yes"),
                "tts_auto_play": tts_auto_play.strip().lower() in ("1", "true", "on", "yes"),
                "tts_backend": (tts_backend or existing.get("tts_backend") or "edge").strip().lower(),
                "tts_rate": max(0.5, min(rate, 2.0)),
                "tts_voice": tts_voice.strip(),
                "tts_openai_voice": (tts_openai_voice or existing.get("tts_openai_voice") or "alloy").strip(),
                "tts_openai_api_key": (tts_openai_api_key or existing.get("tts_openai_api_key") or "").strip(),
                "tts_openai_base_url": (
                    tts_openai_base_url or existing.get("tts_openai_base_url") or "https://api.openai.com/v1"
                ).strip(),
                "tts_openai_model": (tts_openai_model or existing.get("tts_openai_model") or "tts-1").strip(),
                "tts_openai_auth_style": (
                    tts_openai_auth_style or existing.get("tts_openai_auth_style") or "bearer"
                ).strip().lower(),
                "tts_openai_voices_json": voices_json_raw,
                "tts_custom": tts_custom,
                "locale": resolve_locale(locale or existing.get("locale")),
                "disabled_extensions": disabled,
                "embedding_provider": (embedding_provider or existing.get("embedding_provider") or "hash").strip(),
                "sd_webui_url": (sd_webui_url or existing.get("sd_webui_url") or "").strip(),
            },
        )
        runtime.commit()
    finally:
        runtime.close()
    return RedirectResponse(url="/settings", status_code=303)


@app.post("/settings/import-preset")
async def import_st_preset_settings(file: UploadFile = File(...)) -> RedirectResponse:
    from novel_world.modules.ai.services.st_preset_codec import apply_preset_to_prefs, parse_st_preset

    data = await file.read()
    preset = parse_st_preset(data)
    runtime = _ctx().open()
    try:
        existing = get_user_prefs(runtime.session.connection)
        save_user_prefs(
            runtime.session.connection,
            apply_preset_to_prefs(existing, preset),
        )
        runtime.commit()
    finally:
        runtime.close()
    return RedirectResponse(url="/settings", status_code=303)


@app.get("/guide", response_class=HTMLResponse)
def guide_page(request: Request) -> HTMLResponse:
    nav = _nav_context(request, active="guide")
    nav["author_credit_line"] = AUTHOR_CREDIT_LINE
    return templates.TemplateResponse(request, "guide.html", nav)


@app.post("/settings/extensions")
async def update_extensions(request: Request) -> RedirectResponse:
    form = await request.form()
    enabled = set(form.getlist("enabled"))
    runtime = _ctx().open()
    try:
        all_ids = [
            e["id"]
            for e in runtime.extensions
            if e.get("status") in ("ok", "disabled")
        ]
        disabled = [eid for eid in all_ids if eid not in enabled]
        existing = get_user_prefs(runtime.session.connection)
        save_user_prefs(
            runtime.session.connection,
            {**existing, "disabled_extensions": disabled},
        )
        runtime.commit()
    finally:
        runtime.close()
    return RedirectResponse(url="/settings", status_code=303)


@app.get("/mods/{mod_id}/{asset_path:path}")
def mod_asset(mod_id: str, asset_path: str) -> FileResponse:
    config = default_config(PROJECT_ROOT)
    resolved = resolve_mod_asset_path(config.mods_dir, mod_id, asset_path)
    if resolved is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Not found")
    suffix = resolved.suffix.lower()
    media = "application/octet-stream"
    if suffix == ".js":
        media = "text/javascript; charset=utf-8"
    elif suffix == ".css":
        media = "text/css; charset=utf-8"
    return FileResponse(resolved, media_type=media)


@app.post("/settings/mods/install")
async def install_mod_upload(file: UploadFile = File(...)) -> RedirectResponse:
    data = await file.read()
    config = default_config(PROJECT_ROOT)
    result = install_mod_zip(config.mods_dir, data, filename=file.filename or "")
    if not result.get("ok"):
        raise ValidationError(str(result.get("message") or "安装失败"))
    return RedirectResponse(url="/settings", status_code=303)


@app.post("/settings/mods/uninstall")
async def uninstall_mod_route(mod_id: str = Form(...)) -> RedirectResponse:
    config = default_config(PROJECT_ROOT)
    result = uninstall_mod(config.mods_dir, (mod_id or "").strip())
    if not result.get("ok"):
        raise ValidationError(str(result.get("message") or "卸载失败"))
    return RedirectResponse(url="/settings", status_code=303)


@app.post("/settings/mods/import-world")
async def import_world_mod_pack(file: UploadFile = File(...)) -> RedirectResponse:
    data = await file.read()
    runtime = _ctx().open()
    try:
        result = runtime.world_pack.import_world(data)
        runtime.commit()
        world_id = result.get("world_id") or ""
        return RedirectResponse(url=f"/worlds/{world_id}", status_code=303)
    finally:
        runtime.close()


@app.get("/api/providers/catalog")
def provider_catalog_api() -> JSONResponse:
    ctx = _ctx()
    runtime = ctx.open()

    try:
        providers = runtime.providers.list_all()
        catalog = _catalog_with_status(providers)
        options = _build_provider_options(runtime.providers.list_enabled())
    finally:
        runtime.close()
    return JSONResponse({"catalog": catalog, "options": options})


@app.post("/settings/providers/create")
def create_provider(
    name: str = Form(...),
    provider_type: str = Form(default=""),
    api_key: str = Form(default=""),
    base_url: str = Form(default=""),
    model: str = Form(default=""),
    preset_slug: str = Form(default=""),
) -> RedirectResponse:
    ctx = _ctx()
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
        runtime.providers.create(resolved_name, resolved_type, config)  # type: ignore[arg-type]
        runtime.commit()
    finally:
        runtime.close()
    return RedirectResponse(url="/settings", status_code=303)


@app.post("/settings/providers/{provider_id}/delete")
def delete_provider(provider_id: str) -> RedirectResponse:
    ctx = _ctx()
    runtime = ctx.open()

    try:
        removed_sessions = runtime.chat.delete_sessions_by_provider(provider_id)
        runtime.providers.delete(provider_id)
        runtime.commit()
        if removed_sessions:
            msg = f"已删除提供商，并清理了 {removed_sessions} 个关联对话。"
        else:
            msg = "已删除提供商。"
        return RedirectResponse(url=f"/settings?status=success&msg={quote(msg)}", status_code=303)
    except Exception as e:  # noqa: BLE001
        runtime.rollback()
        msg = f"删除失败：{e}"
        return RedirectResponse(url=f"/settings?status=error&msg={quote(msg)}", status_code=303)
    finally:
        runtime.close()


@app.post("/settings/providers/{provider_id}/test")
def test_provider(provider_id: str, model: str = Form(default="")) -> RedirectResponse:
    ctx = _ctx()
    runtime = ctx.open()

    try:
        reply = runtime.providers.test_connection(provider_id, model=model or None)
        runtime.commit()
        msg = f"连接成功：{reply[:80]}"
        return RedirectResponse(url=f"/settings?status=success&msg={quote(msg)}", status_code=303)
    except Exception as e:
        runtime.rollback()
        msg = str(e)
        return RedirectResponse(url=f"/settings?status=error&msg={quote(msg)}", status_code=303)
    finally:
        runtime.close()


@app.post("/api/providers/{provider_id}/test")
def test_provider_api(provider_id: str, model: str = Form(default="")) -> JSONResponse:
    ctx = _ctx()
    runtime = ctx.open()

    try:
        reply = runtime.providers.test_connection(provider_id, model=model or None)
        runtime.commit()
        return JSONResponse({"ok": True, "message": "连接成功", "reply": reply[:200]})
    except Exception as e:
        runtime.rollback()
        return JSONResponse({"ok": False, "message": str(e)}, status_code=400)
    finally:
        runtime.close()


@app.get("/api/providers/{provider_id}/models")
def provider_models_api(provider_id: str) -> JSONResponse:
    ctx = _ctx()
    runtime = ctx.open()

    try:
        payload = runtime.providers.list_available_models(provider_id)
        return JSONResponse({"ok": True, **payload})
    except Exception as e:
        return JSONResponse({"ok": False, "message": str(e), "models": [], "source": "catalog"}, status_code=400)
    finally:
        runtime.close()


@app.post("/api/providers/discover/models")
def discover_provider_models_api(
    provider_type: str = Form(...),
    api_key: str = Form(default=""),
    base_url: str = Form(default=""),
) -> JSONResponse:
    ctx = _ctx()
    runtime = ctx.open()

    try:
        payload = runtime.providers.discover_models(
            provider_type,  # type: ignore[arg-type]
            api_key=api_key.strip(),
            base_url=base_url.strip(),
        )
        return JSONResponse({"ok": True, **payload})
    except Exception as e:
        return JSONResponse({"ok": False, "message": str(e), "models": []}, status_code=400)
    finally:
        runtime.close()


@app.post("/api/server/stop")
def stop_server(request: Request) -> JSONResponse:
    if not _is_localhost(request):
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
    config = _ctx().config
    remove_server_meta(config.data_dir)
    threading.Timer(0.5, os._exit, args=(0,)).start()
    return JSONResponse({"ok": True})


# ---------- Chat ----------


@app.get("/chat", response_class=HTMLResponse)
def chat_page(request: Request, session_id: str | None = None) -> HTMLResponse:
    ctx = _ctx()
    runtime = ctx.open()

    try:
        sessions = runtime.chat.list_sessions(world_id=None)
        providers = runtime.providers.list_enabled()
        current = None
        messages = []
        if session_id:
            current = runtime.chat.get_session(session_id)
            messages = runtime.chat.get_messages(session_id)
        elif sessions:
            current = sessions[0]
            messages = runtime.chat.get_messages(current.id)
        session_attachments = (
            runtime.documents.list_session_attachments(current.id) if current else []
        )
        memories = runtime.memory.list(current.id) if current else []
        page_extras = _session_page_extras(runtime, current)
    finally:
        runtime.close()

    nav = _nav_context(request, active="chat")
    nav.update(
        {
            "sessions": sessions,
            "current_session": current,
            "messages": messages,
            "providers": providers,
            "provider_options": _build_provider_options(providers),
            "provider_option_groups": _build_provider_option_groups(providers),
            "session_attachments": session_attachments,
            "memories": memories,
            "world_id": None,
            "world": None,
            "characters": [],
            "worlds": _list_worlds(),
            "persona_update_url": (
                f"/chat/sessions/{current.id}/update-persona" if current else ""
            ),
            **_user_persona_nav(current),
            **page_extras,
        }
    )
    return templates.TemplateResponse(request, "chat.html", nav)


@app.get("/worlds/{world_id}/chat", response_class=HTMLResponse)
def world_chat_page(request: Request, world_id: str, session_id: str | None = None) -> HTMLResponse:
    ctx = _ctx()
    runtime = ctx.open()
    world_app = _world_app()
    wrt = world_app.open_world(WorldId(world_id))
    try:
        world = wrt.world.get(WorldId(world_id))
        characters = wrt.character.list_by_world(WorldId(world_id), active_only=False)
        sessions = runtime.chat.list_sessions(world_id=world_id)
        providers = runtime.providers.list_enabled()
        current = None
        messages = []
        if session_id:
            current = runtime.chat.get_session(session_id)
            messages = runtime.chat.get_messages(session_id)
        elif sessions:
            current = sessions[0]
            messages = runtime.chat.get_messages(current.id)
        session_attachments = (
            runtime.documents.list_session_attachments(current.id) if current else []
        )
        memories = runtime.memory.list(current.id) if current else []
        page_extras = _session_page_extras(runtime, current)
    finally:
        runtime.close()
        wrt.close()

    character_avatars = {
        str(c.id): f"/api/worlds/{world_id}/characters/{c.id}/avatar"
        for c in characters
        if get_avatar_relpath(c)
    }
    message_speakers: dict[str, dict[str, str]] = {}
    for m in messages:
        if m.role == "assistant":
            sp = resolve_message_speaker(m, world_id, world_app, characters)
            if sp:
                message_speakers[m.id] = sp

    from novel_world.modules.ai.services.tts_voice_resolver import extract_tts_voice_from_character

    world_characters_json = [
        {
            "id": str(c.id),
            "name": c.name,
            "role": c.role,
            "avatar_url": character_avatars.get(str(c.id), ""),
            "tts_voice": extract_tts_voice_from_character(c),
        }
        for c in characters
    ]

    nav = _nav_context(request, active="chat", world_name=world.name)
    nav.update(
        {
            "sessions": sessions,
            "current_session": current,
            "messages": messages,
            "message_speakers": message_speakers,
            "world_characters_json": world_characters_json,
            "providers": providers,
            "provider_options": _build_provider_options(providers),
            "provider_option_groups": _build_provider_option_groups(providers),
            "session_attachments": session_attachments,
            "memories": memories,
            "world_id": world_id,
            "world": world,
            "characters": characters,
            "character_avatars": character_avatars,
            "worlds": _list_worlds(),
            "persona_update_url": (
                f"/chat/sessions/{current.id}/update-persona" if current else ""
            ),
            **_user_persona_nav(current, world),
            **page_extras,
        }
    )
    return templates.TemplateResponse(request, "chat.html", nav)


@app.post("/chat/sessions/{session_id}/update-persona")
def update_chat_persona(
    session_id: str,
    persona_name: str = Form(default=""),
    persona_description: str = Form(default=""),
    world_id: str = Form(default=""),
) -> RedirectResponse:
    ctx = _ctx()
    runtime = ctx.open()
    try:
        runtime.chat.update_persona(
            session_id, name=persona_name, description=persona_description
        )
        runtime.commit()
    finally:
        runtime.close()
    if world_id.strip():
        url = f"/worlds/{world_id.strip()}/chat?session_id={session_id}"
    else:
        url = f"/chat?session_id={session_id}"
    return RedirectResponse(url=url, status_code=303)


@app.post("/chat/sessions/create")
def create_chat_session(
    provider_id: str = Form(...),
    model: str = Form(default=""),
    world_id: str = Form(default=""),
) -> RedirectResponse:
    if provider_id.startswith("preset:"):
        slug = provider_id.removeprefix("preset:")
        return RedirectResponse(url=f"/settings?preset={slug}", status_code=303)

    ctx = _ctx()
    runtime = ctx.open()

    try:
        wid = world_id.strip() or None
        resolved_id = runtime.providers.resolve_provider_ref(provider_id)
        session = runtime.chat.create_session(resolved_id, model, world_id=wid)
        runtime.commit()
    finally:
        runtime.close()
    if wid:
        return RedirectResponse(url=f"/worlds/{wid}/chat?session_id={session.id}", status_code=303)
    return RedirectResponse(url=f"/chat?session_id={session.id}", status_code=303)


@app.post("/chat/sessions/{session_id}/send")
def send_chat_message(
    session_id: str,
    content: str = Form(...),
    world_id: str = Form(default=""),
) -> RedirectResponse:
    ctx = _ctx()
    runtime = ctx.open()

    try:
        runtime.chat.send_message(session_id, content)
        runtime.commit()
    finally:
        runtime.close()
    wid = world_id.strip()
    if wid:
        return RedirectResponse(
            url=f"/worlds/{wid}/chat?session_id={session_id}", status_code=303
        )
    return RedirectResponse(url=f"/chat?session_id={session_id}", status_code=303)


@app.post("/chat/sessions/{session_id}/delete")
def delete_chat_session(session_id: str, world_id: str = Form(default="")) -> RedirectResponse:
    ctx = _ctx()
    runtime = ctx.open()

    try:
        runtime.chat.delete_session(session_id)
        runtime.commit()
    finally:
        runtime.close()
    wid = world_id.strip()
    if wid:
        return RedirectResponse(url=f"/worlds/{wid}/chat", status_code=303)
    return RedirectResponse(url="/chat", status_code=303)


@app.post("/api/chat/sessions/{session_id}/stream")
async def stream_chat_message(
    session_id: str,
    content: str = Form(default=""),
    message_attachment_ids: str = Form(default=""),
    mode: str = Form(default="chat"),
) -> StreamingResponse:
    att_ids = [x.strip() for x in message_attachment_ids.split(",") if x.strip()]

    def event_generator():
        ctx = _ctx()
        runtime = ctx.open()
        try:
            for chunk in runtime.chat.stream_message(
                session_id, content, message_attachment_ids=att_ids or None, mode=mode
            ):
                payload = json.dumps({"kind": chunk.kind, "text": chunk.text}, ensure_ascii=False)
                yield f"event: {chunk.kind}\ndata: {payload}\n\n"
            runtime.commit()
        except Exception as e:
            runtime.rollback()
            err = json.dumps({"kind": "error", "text": str(e)}, ensure_ascii=False)
            yield f"event: error\ndata: {err}\n\n"
        finally:
            runtime.close()

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ---------- Group chat ----------


@app.get("/group-chat", response_class=HTMLResponse)
def group_chat_page(request: Request, session_id: str | None = None) -> HTMLResponse:
    ctx = _ctx()
    runtime = ctx.open()
    try:
        sessions = runtime.group_chat.list_sessions()
        providers = runtime.providers.list_enabled()
        current = None
        messages = []
        members = []
        if session_id:
            current = runtime.group_chat.get_session(session_id)
            messages = runtime.group_chat.get_messages(session_id)
            members = runtime.group_chat.get_members(session_id)
        elif sessions:
            current = sessions[0]
            messages = runtime.group_chat.get_messages(current.id)
            members = runtime.group_chat.get_members(current.id)
        memories = runtime.memory.list(current.id) if current else []
        page_extras = _session_page_extras(runtime, current)
    finally:
        runtime.close()

    mention_members = [
        {
            "character_id": m.character_id,
            "character_name": m.character_name,
            "world_name": m.world_name,
        }
        for m in members
    ]

    nav = _nav_context(request, active="group_chat")
    nav.update(
        {
            "sessions": sessions,
            "current_session": current,
            "messages": messages,
            "members": members,
            "mention_members": mention_members,
            "memories": memories,
            "providers": providers,
            "provider_option_groups": _build_provider_option_groups(providers),
            "world_tree": _list_worlds_with_characters(),
            "persona_update_url": (
                f"/group-chat/sessions/{current.id}/update-persona" if current else ""
            ),
            **_user_persona_nav(current),
            **page_extras,
        }
    )
    return templates.TemplateResponse(request, "group_chat.html", nav)


@app.post("/group-chat/sessions/{session_id}/update-persona")
def update_group_persona(
    session_id: str,
    persona_name: str = Form(default=""),
    persona_description: str = Form(default=""),
) -> RedirectResponse:
    ctx = _ctx()
    runtime = ctx.open()
    try:
        runtime.group_chat.update_persona(
            session_id, name=persona_name, description=persona_description
        )
        runtime.commit()
    finally:
        runtime.close()
    return RedirectResponse(
        url=f"/group-chat?session_id={session_id}", status_code=303
    )


@app.get("/api/worlds/characters")
def api_worlds_characters() -> JSONResponse:
    return JSONResponse({"worlds": _list_worlds_with_characters()})


@app.post("/group-chat/sessions/create")
def create_group_session(
    provider_id: str = Form(...),
    model: str = Form(default=""),
    title: str = Form(default=""),
    members: str = Form(default="[]"),
) -> RedirectResponse:
    if provider_id.startswith("preset:"):
        slug = provider_id.removeprefix("preset:")
        return RedirectResponse(url=f"/settings?preset={slug}", status_code=303)

    try:
        member_list = json.loads(members)
        if not isinstance(member_list, list):
            member_list = []
    except json.JSONDecodeError:
        member_list = []

    ctx = _ctx()
    runtime = ctx.open()
    try:
        resolved_id = runtime.providers.resolve_provider_ref(provider_id)
        session = runtime.group_chat.create_group(
            resolved_id, model, title=title, members=member_list
        )
        runtime.commit()
    finally:
        runtime.close()
    return RedirectResponse(url=f"/group-chat?session_id={session.id}", status_code=303)


@app.post("/group-chat/sessions/{session_id}/delete")
def delete_group_session(session_id: str) -> RedirectResponse:
    ctx = _ctx()
    runtime = ctx.open()
    try:
        runtime.group_chat.delete_session(session_id)
        runtime.commit()
    finally:
        runtime.close()
    return RedirectResponse(url="/group-chat", status_code=303)


@app.post("/api/group-chat/sessions/{session_id}/stream")
async def stream_group_message(
    session_id: str,
    content: str = Form(default=""),
    mode: str = Form(default="send"),
    max_round: int = Form(default=0),
    max_replies: int = Form(default=0),
    max_total: int = Form(default=0),
    max_per_character: int = Form(default=0),
    force_character_id: str = Form(default=""),
) -> StreamingResponse:
    def event_generator():
        ctx = _ctx()
        runtime = ctx.open()
        try:
            for evt in runtime.group_chat.reply_round(
                session_id,
                content=content,
                mode=mode,
                max_round=max_round,
                max_replies=max_replies,
                max_total=max_total,
                max_per_character=max_per_character,
                force_character_id=force_character_id,
            ):
                payload = json.dumps(evt["data"], ensure_ascii=False)
                yield f"event: {evt['event']}\ndata: {payload}\n\n"
                runtime.commit()
        except Exception as e:
            runtime.rollback()
            err = json.dumps({"message": str(e)}, ensure_ascii=False)
            yield f"event: error\ndata: {err}\n\n"
        finally:
            runtime.close()

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/api/group-chat/sessions/{session_id}/stop")
def stop_group_session(session_id: str) -> JSONResponse:
    ctx = _ctx()
    runtime = ctx.open()
    try:
        runtime.group_chat.request_stop(session_id)
    finally:
        runtime.close()
    return JSONResponse({"ok": True})


@app.post("/api/group-chat/sessions/{session_id}/members/add")
async def group_add_members(request: Request, session_id: str) -> JSONResponse:
    body = await request.json()
    members = body.get("members") if isinstance(body, dict) else []
    if not isinstance(members, list):
        members = []
    ctx = _ctx()
    runtime = ctx.open()
    try:
        updated = runtime.group_chat.add_members(session_id, members)
        runtime.commit()
        return JSONResponse(
            {
                "ok": True,
                "members": [
                    {
                        "world_id": m.world_id,
                        "character_id": m.character_id,
                        "character_name": m.character_name,
                        "world_name": m.world_name,
                    }
                    for m in updated
                ],
            }
        )
    except Exception as e:
        runtime.rollback()
        return JSONResponse({"ok": False, "message": str(e)}, status_code=400)
    finally:
        runtime.close()


@app.post("/api/group-chat/sessions/{session_id}/members/remove")
async def group_remove_member(request: Request, session_id: str) -> JSONResponse:
    body = await request.json()
    if not isinstance(body, dict):
        body = {}
    ctx = _ctx()
    runtime = ctx.open()
    try:
        updated = runtime.group_chat.remove_member(
            session_id,
            str(body.get("world_id") or ""),
            str(body.get("character_id") or ""),
        )
        runtime.commit()
        return JSONResponse(
            {
                "ok": True,
                "members": [
                    {
                        "world_id": m.world_id,
                        "character_id": m.character_id,
                        "character_name": m.character_name,
                        "world_name": m.world_name,
                    }
                    for m in updated
                ],
            }
        )
    except Exception as e:
        runtime.rollback()
        return JSONResponse({"ok": False, "message": str(e)}, status_code=400)
    finally:
        runtime.close()


@app.post("/api/group-chat/sessions/{session_id}/members/mute")
async def group_mute_member(request: Request, session_id: str) -> JSONResponse:
    body = await request.json()
    if not isinstance(body, dict):
        body = {}
    ctx = _ctx()
    runtime = ctx.open()
    try:
        session = runtime.group_chat.set_member_muted(
            session_id,
            str(body.get("character_id") or ""),
            muted=bool(body.get("muted", True)),
        )
        runtime.commit()
        return JSONResponse(
            {
                "ok": True,
                "muted": list((session.config or {}).get("muted") or []),
            }
        )
    except Exception as e:
        runtime.rollback()
        return JSONResponse({"ok": False, "message": str(e)}, status_code=400)
    finally:
        runtime.close()


# ---------- Roleplay ----------


@app.get("/worlds/{world_id}/roleplay/{character_id}/chat", response_class=HTMLResponse)
def roleplay_chat_page(
    request: Request,
    world_id: str,
    character_id: str,
    session_id: str | None = None,
) -> HTMLResponse:
    app_factory = _world_app()
    wrt = app_factory.open_world(WorldId(world_id))
    ctx = _ctx()
    runtime = ctx.open()
    try:
        world = wrt.world.get(WorldId(world_id))
        character = wrt.character.get(CharacterId(character_id))
        card_svc = CharacterCardService(
            app_factory.config,
            SqliteCharacterRepository(wrt.session.connection),
        )
        avatar_url = card_svc.avatar_url(world_id, character_id)
        has_avatar = card_svc.character_avatar_path(world_id, character_id) is not None

        sessions = runtime.roleplay.list_sessions(world_id, character_id)
        providers = runtime.providers.list_enabled()
        current = None
        messages = []
        if session_id:
            current = runtime.roleplay.get_session(session_id)
            messages = runtime.roleplay.get_messages(session_id)
        elif sessions:
            current = sessions[0]
            messages = runtime.roleplay.get_messages(current.id)

        persona_nav = _user_persona_nav(current, world)
        memories = runtime.memory.list(current.id) if current else []
        page_extras = _session_page_extras(runtime, current)

        profile = character.profile or {}
        from novel_world.modules.ai.services.roleplay_service import _greeting_options

        greeting_options = _greeting_options(profile)
        greeting_index = int((current.config or {}).get("greeting_index") or 0) if current else 0
        has_user_messages = any(m.role == "user" for m in messages) if messages else False
    finally:
        runtime.close()
        wrt.close()

    nav = _nav_context(request, active="roleplay", world_name=world.name)
    nav.update(
        {
            "world_id": world_id,
            "world": world,
            "character": character,
            "character_id": character_id,
            "avatar_url": avatar_url if has_avatar else "",
            "sessions": sessions,
            "current_session": current,
            "messages": messages,
            "providers": providers,
            "provider_option_groups": _build_provider_option_groups(providers),
            "worlds": _list_worlds(),
            "persona_update_url": (
                f"/roleplay/sessions/{current.id}/update-persona" if current else ""
            ),
            **persona_nav,
            "memories": memories,
            **page_extras,
            "greeting_options": greeting_options,
            "greeting_index": greeting_index,
            "can_switch_greeting": bool(
                current and len(greeting_options) > 1 and not has_user_messages
            ),
        }
    )
    wrt2 = app_factory.open_world(WorldId(world_id))
    try:
        nav["characters"] = wrt2.character.list_by_world(WorldId(world_id), active_only=False)
    finally:
        wrt2.close()
    return templates.TemplateResponse(request, "roleplay.html", nav)


@app.post("/roleplay/sessions/create")
def create_roleplay_session(
    provider_id: str = Form(...),
    model: str = Form(default=""),
    world_id: str = Form(...),
    character_id: str = Form(...),
    persona_name: str = Form(default=""),
    persona_description: str = Form(default=""),
    title: str = Form(default=""),
) -> RedirectResponse:
    if provider_id.startswith("preset:"):
        slug = provider_id.removeprefix("preset:")
        return RedirectResponse(url=f"/settings?preset={slug}", status_code=303)

    ctx = _ctx()
    runtime = ctx.open()
    try:
        resolved_id = runtime.providers.resolve_provider_ref(provider_id)
        explicit_persona = None
        if persona_name.strip() or persona_description.strip():
            explicit_persona = store_persona(persona_name, persona_description)
        session = runtime.roleplay.create_session(
            resolved_id,
            model,
            world_id=world_id,
            character_id=character_id,
            user_persona=explicit_persona,
            title=title,
        )
        runtime.commit()
    finally:
        runtime.close()
    return RedirectResponse(
        url=f"/worlds/{world_id}/roleplay/{character_id}/chat?session_id={session.id}",
        status_code=303,
    )


@app.post("/roleplay/sessions/{session_id}/delete")
def delete_roleplay_session(
    session_id: str,
    world_id: str = Form(...),
    character_id: str = Form(...),
) -> RedirectResponse:
    ctx = _ctx()
    runtime = ctx.open()
    try:
        runtime.roleplay.delete_session(session_id)
        runtime.commit()
    finally:
        runtime.close()
    return RedirectResponse(
        url=f"/worlds/{world_id}/roleplay/{character_id}/chat",
        status_code=303,
    )


@app.post("/api/roleplay/sessions/{session_id}/greeting")
async def set_roleplay_greeting(session_id: str, request: Request) -> JSONResponse:
    body = await request.json()
    index = int(body.get("greeting_index", 0) if isinstance(body, dict) else 0)
    ctx = _ctx()
    runtime = ctx.open()
    try:
        session = runtime.roleplay.set_greeting_index(session_id, index)
        messages = runtime.roleplay.get_messages(session_id)
        runtime.commit()
        first = next((m for m in messages if m.role == "assistant"), None)
        return JSONResponse(
            {
                "ok": True,
                "greeting_index": int((session.config or {}).get("greeting_index") or 0),
                "first_message": first.content if first else "",
            }
        )
    except Exception as e:
        runtime.rollback()
        return JSONResponse({"ok": False, "message": str(e)}, status_code=400)
    finally:
        runtime.close()


@app.post("/roleplay/sessions/{session_id}/update-persona")
def update_roleplay_persona(
    session_id: str,
    world_id: str = Form(...),
    character_id: str = Form(...),
    persona_name: str = Form(default=""),
    persona_description: str = Form(default=""),
) -> RedirectResponse:
    ctx = _ctx()
    runtime = ctx.open()
    try:
        runtime.roleplay.update_persona(
            session_id, name=persona_name, description=persona_description
        )
        runtime.commit()
    finally:
        runtime.close()
    return RedirectResponse(
        url=f"/worlds/{world_id}/roleplay/{character_id}/chat?session_id={session_id}",
        status_code=303,
    )


@app.post("/api/roleplay/sessions/{session_id}/stream")
async def stream_roleplay_message(
    session_id: str,
    content: str = Form(default=""),
) -> StreamingResponse:
    def event_generator():
        ctx = _ctx()
        runtime = ctx.open()
        try:
            for chunk in runtime.roleplay.stream_message(session_id, content):
                payload = json.dumps({"kind": chunk.kind, "text": chunk.text}, ensure_ascii=False)
                yield f"event: {chunk.kind}\ndata: {payload}\n\n"
            runtime.commit()
        except Exception as e:
            runtime.rollback()
            err = json.dumps({"kind": "error", "text": str(e)}, ensure_ascii=False)
            yield f"event: error\ndata: {err}\n\n"
        finally:
            runtime.close()

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/api/chat/sessions/{session_id}/attachments")
async def upload_session_attachment(
    session_id: str,
    file: UploadFile = File(...),
    scope: str = Form(default="session"),
) -> JSONResponse:
    ctx = _ctx()
    runtime = ctx.open()

    try:
        data = await file.read()
        att = runtime.documents.upload_chat_attachment(
            session_id,
            file.filename or "upload.bin",
            data,
            mime_type=file.content_type or "",
            message_id=None if scope == "session" else scope,
        )
        runtime.commit()
        return JSONResponse({"ok": True, "id": att.id, "filename": att.filename})
    except Exception as e:
        runtime.rollback()
        return JSONResponse({"ok": False, "message": str(e)}, status_code=400)
    finally:
        runtime.close()


@app.post("/api/documents/extract-text")
async def extract_document_text(file: UploadFile = File(...)) -> JSONResponse:
    try:
        data = await file.read()
        text = extract_text_from_bytes(file.filename or "", data)
        return JSONResponse({"ok": True, "text": text, "filename": file.filename or ""})
    except (DomainError, ValidationError) as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=400)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "message": str(e)}, status_code=400)


@app.post("/api/chat/sessions/{session_id}/attachments/{attachment_id}/delete")
def delete_session_attachment(session_id: str, attachment_id: str) -> JSONResponse:
    ctx = _ctx()
    runtime = ctx.open()

    try:
        runtime.documents.delete_chat_attachment(attachment_id)
        runtime.commit()
        return JSONResponse({"ok": True})
    except Exception as e:
        runtime.rollback()
        return JSONResponse({"ok": False, "message": str(e)}, status_code=400)
    finally:
        runtime.close()


# ---------- Worlds (existing) ----------


@app.get("/worlds", response_class=HTMLResponse)
def worlds_page(request: Request, data_dir: str | None = None, import_error: str | None = None) -> HTMLResponse:
    base_dir = _data_dir_from_form(data_dir)
    worlds = _list_worlds(base_dir or PROJECT_ROOT)
    nav = _nav_context(request, active="worlds")
    nav["worlds"] = worlds
    nav["import_error"] = import_error
    return templates.TemplateResponse(request, "worlds.html", nav)


@app.post("/worlds/create")
def create_world(
    name: str = Form(...),
    description: str = Form(default=""),
    genre: str = Form(default=""),
    rules_json: str = Form(default="{}"),
    settings_json: str = Form(default="{}"),
) -> RedirectResponse:
    rules = _json_loads_maybe(rules_json, default={})
    settings = _json_loads_maybe(settings_json, default={})
    world = CreateWorldUseCase(base_dir=PROJECT_ROOT).execute(
        name, description=description, genre=genre, rules=rules, settings=settings
    )
    return RedirectResponse(url=f"/worlds/{world.id}", status_code=303)


@app.post("/worlds/{world_id}/delete")
def delete_world(world_id: str) -> RedirectResponse:
    app_factory = _world_app()
    app_factory.delete_world(WorldId(world_id))
    ctx = _ctx()
    runtime = ctx.open()

    try:
        runtime.chat.delete_sessions_by_world(world_id)
        runtime.commit()
    finally:
        runtime.close()
    return RedirectResponse(url="/worlds", status_code=303)


@app.get("/worlds/{world_id}", response_class=HTMLResponse)
def world_detail(request: Request, world_id: str) -> HTMLResponse:
    app_factory = _world_app()
    rt = app_factory.open_world(WorldId(world_id))
    try:
        world = rt.world.get(WorldId(world_id))
        characters = rt.character.list_by_world(world.id, active_only=False)
        state_entries = rt.state.list_by_world(world.id)
        events = rt.event.list_by_world(world.id)
        saves = rt.save.list_saves(world.id)
        ctx = _ctx()
        rt_docs = ctx.open()
        try:
            world_documents = rt_docs.documents.list_world_documents(world_id)
        finally:
            rt_docs.close()
        nav = _nav_context(request, active="worlds", world_name=world.name)
        nav.update(
            {
                "world": world,
                "characters": characters,
                "state_entries": state_entries,
                "events": events[-50:],
                "saves": saves,
                "world_documents": world_documents,
                "lore_entries": rt.lore.list_entries(include_disabled=True),
                "rules_pretty": json.dumps(world.rules, ensure_ascii=False, indent=2) if world.rules else "",
                "settings_pretty": json.dumps(world.settings, ensure_ascii=False, indent=2) if world.settings else "",
                "world_background_url": _world_background_url(world_id),
                "world_user_persona": persona_from_world_settings(
                    world.settings if isinstance(world.settings, dict) else {}
                ),
            }
        )
        return templates.TemplateResponse(request, "world_detail.html", nav)
    finally:
        rt.close()


@app.post("/worlds/{world_id}/update")
def update_world(
    world_id: str,
    name: str = Form(...),
    description: str = Form(default=""),
    genre: str = Form(default=""),
    rules_json: str = Form(default="{}"),
    settings_json: str = Form(default="{}"),
) -> RedirectResponse:
    app_factory = _world_app()
    rt = app_factory.open_world(WorldId(world_id))
    try:
        rules = _json_loads_maybe(rules_json, default={})
        settings = _json_loads_maybe(settings_json, default={})
        existing = rt.world.get(WorldId(world_id))
        old_settings = existing.settings if isinstance(existing.settings, dict) else {}
        if "background" in old_settings and "background" not in settings:
            settings["background"] = old_settings["background"]
        rt.world.update(
            WorldId(world_id),
            name=name,
            description=description,
            genre=genre,
            rules=rules,
            settings=settings,
        )
        rt.session.commit()
    finally:
        rt.close()
    return RedirectResponse(url=f"/worlds/{world_id}", status_code=303)


@app.post("/worlds/{world_id}/update-user-persona")
def update_world_user_persona(
    world_id: str,
    persona_name: str = Form(default=""),
    persona_description: str = Form(default=""),
) -> RedirectResponse:
    app_factory = _world_app()
    rt = app_factory.open_world(WorldId(world_id))
    try:
        world = rt.world.get(WorldId(world_id))
        settings = dict(world.settings) if isinstance(world.settings, dict) else {}
        settings["user_persona"] = store_persona(persona_name, persona_description)
        rt.world.update(WorldId(world_id), settings=settings)
        rt.session.commit()
    finally:
        rt.close()
    ctx = _ctx()
    runtime = ctx.open()
    try:
        runtime.chat.clear_world_cache(world_id)
    finally:
        runtime.close()
    return RedirectResponse(url=f"/worlds/{world_id}", status_code=303)


@app.post("/worlds/{world_id}/characters/create")
def create_character(
    world_id: str,
    name: str = Form(...),
    role: str = Form(default="npc"),
    summary: str = Form(default=""),
    personality: str = Form(default=""),
    appearance: str = Form(default=""),
    background: str = Form(default=""),
    attributes_json: str = Form(default="{}"),
) -> RedirectResponse:
    app_factory = _world_app()
    rt = app_factory.open_world(WorldId(world_id))
    try:
        profile = {
            k: v
            for k, v in {
                "summary": summary.strip(),
                "personality": personality.strip(),
                "appearance": appearance.strip(),
                "background": background.strip(),
            }.items()
            if v
        }
        attributes = _json_loads_maybe(attributes_json, default={})
        rt.character.create(
            WorldId(world_id), name, role=normalize_role(role), profile=profile, attributes=attributes
        )
        rt.session.commit()
    finally:
        rt.close()
    return RedirectResponse(url=f"/worlds/{world_id}", status_code=303)


@app.post("/worlds/{world_id}/characters/{character_id}/update")
def update_character(
    world_id: str,
    character_id: str,
    name: str = Form(...),
    role: str = Form(default="npc"),
    summary: str = Form(default=""),
    personality: str = Form(default=""),
    appearance: str = Form(default=""),
    background: str = Form(default=""),
    scenario: str = Form(default=""),
    first_mes: str = Form(default=""),
    mes_example: str = Form(default=""),
    post_history_instructions: str = Form(default=""),
    tts_voice: str = Form(default=""),
    attributes_json: str = Form(default="{}"),
    relationships_json: str = Form(default="[]"),
) -> RedirectResponse:
    app_factory = _world_app()
    rt = app_factory.open_world(WorldId(world_id))
    try:
        existing = rt.character.get(CharacterId(character_id))
        existing_profile = dict(existing.profile or {})
        profile = {
            k: v
            for k, v in {
                "summary": summary.strip(),
                "personality": personality.strip(),
                "appearance": appearance.strip(),
                "background": background.strip(),
                "description": summary.strip() or existing_profile.get("description", ""),
                "scenario": scenario.strip(),
                "first_mes": first_mes.strip(),
                "mes_example": mes_example.strip(),
                "post_history_instructions": post_history_instructions.strip(),
            }.items()
            if v or k in ("scenario", "first_mes", "mes_example", "post_history_instructions")
        }
        # 保留未在表单中的 profile 键
        for key, val in existing_profile.items():
            if key not in profile and val:
                profile[key] = val
        attributes = _json_loads_maybe(attributes_json, default={})
        metadata = dict(existing.metadata or {})
        metadata["relationships"] = _normalize_relationships(
            _json_loads_maybe(relationships_json, default=[])
        )
        metadata["tts_voice"] = tts_voice.strip()
        rt.character.update(
            CharacterId(character_id),
            name=name,
            role=normalize_role(role),
            profile=profile,
            attributes=attributes,
            metadata=metadata,
        )
        updated = rt.character.get(CharacterId(character_id))
        from novel_world.modules.character.services.card_mapper import card_from_character

        meta2 = dict(updated.metadata or {})
        meta2["card"] = card_from_character(updated).to_v2_dict()
        rt.character.update(CharacterId(character_id), metadata=meta2)
        ctx = _ctx()
        runtime = ctx.open()
        try:
            runtime.chat.clear_world_cache(world_id)
            runtime.commit()
        finally:
            runtime.close()
        rt.session.commit()
    finally:
        rt.close()
    return RedirectResponse(url=f"/worlds/{world_id}", status_code=303)


@app.post("/worlds/{world_id}/characters/{character_id}/delete")
def delete_character(world_id: str, character_id: str) -> RedirectResponse:
    app_factory = _world_app()
    rt = app_factory.open_world(WorldId(world_id))
    try:
        rt.character.delete(CharacterId(character_id))
        rt.session.commit()
    finally:
        rt.close()
    return RedirectResponse(url=f"/worlds/{world_id}", status_code=303)


@app.get("/api/worlds/{world_id}/characters/{character_id}/avatar")
def get_character_avatar(world_id: str, character_id: str):
    app_factory, rt, card_svc = _character_card_service(world_id)
    try:
        path = card_svc.character_avatar_path(world_id, character_id)
        if path is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="无头像")
        media = "image/png"
        if path.suffix.lower() in (".jpg", ".jpeg"):
            media = "image/jpeg"
        elif path.suffix.lower() == ".webp":
            media = "image/webp"
        elif path.suffix.lower() == ".gif":
            media = "image/gif"
        return FileResponse(path, media_type=media)
    finally:
        rt.close()


@app.get("/api/worlds/{world_id}/characters/{character_id}/card/export")
def export_character_card(world_id: str, character_id: str, format: str = "json"):
    app_factory, rt, card_svc = _character_card_service(world_id)
    try:
        character = rt.character.get(CharacterId(character_id))
        if format == "png":
            data = card_svc.export_png(character, world_id)
            filename = f"{character.name}.png"
            return StreamingResponse(
                iter([data]),
                media_type="image/png",
                headers={"Content-Disposition": f'attachment; filename="{quote(filename)}"'},
            )
        data = card_svc.export_json(character)
        filename = f"{character.name}.json"
        return StreamingResponse(
            iter([data]),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{quote(filename)}"'},
        )
    finally:
        rt.close()


@app.post("/worlds/{world_id}/characters/{character_id}/import-card")
async def import_character_card(
    world_id: str,
    character_id: str,
    file: UploadFile = File(...),
) -> RedirectResponse:
    app_factory, rt, card_svc = _character_card_service(world_id)
    ctx = _ctx()
    runtime = ctx.open()
    warnings: list[str] = []
    try:
        data = await file.read()
        _, warnings = card_svc.import_card(
            WorldId(world_id), CharacterId(character_id), data, file.filename or ""
        )
        rt.session.commit()
        runtime.chat.clear_world_cache(world_id)
        runtime.commit()
    finally:
        rt.close()
        runtime.close()
    url = f"/worlds/{world_id}"
    if warnings:
        from urllib.parse import quote

        url += f"?card_warn={quote('；'.join(warnings))}"
    return RedirectResponse(url=url, status_code=303)


@app.post("/worlds/{world_id}/characters/import-card")
async def import_new_character_card(
    world_id: str,
    file: UploadFile = File(...),
) -> RedirectResponse:
    app_factory, rt, card_svc = _character_card_service(world_id)
    ctx = _ctx()
    runtime = ctx.open()
    warnings: list[str] = []
    try:
        data = await file.read()
        _, warnings = card_svc.import_card_as_new_character(
            WorldId(world_id), data, file.filename or ""
        )
        rt.session.commit()
        runtime.chat.clear_world_cache(world_id)
        runtime.commit()
    finally:
        rt.close()
        runtime.close()
    url = f"/worlds/{world_id}"
    if warnings:
        from urllib.parse import quote

        url += f"?card_warn={quote('；'.join(warnings))}"
    return RedirectResponse(url=url, status_code=303)


def _avatar_ext_from_filename(filename: str) -> str:
    fn = (filename or "").lower()
    if fn.endswith(".jpg") or fn.endswith(".jpeg"):
        return "jpg"
    if fn.endswith(".webp"):
        return "webp"
    if fn.endswith(".gif"):
        return "gif"
    return "png"


def _resolve_avatar_redirect(
    next_url: str | None,
    world_id: str,
    character_id: str,
    request: Request,
) -> str:
    candidate = (next_url or "").strip()
    if candidate.startswith("/") and not candidate.startswith("//"):
        return candidate
    referer = request.headers.get("referer") or ""
    if "roleplay" in referer:
        parsed = urlparse(referer)
        session_ids = parse_qs(parsed.query).get("session_id", [])
        base = f"/worlds/{world_id}/roleplay/{character_id}/chat"
        if session_ids and session_ids[0]:
            return f"{base}?session_id={session_ids[0]}"
        return base
    return f"/worlds/{world_id}"


@app.post("/api/worlds/{world_id}/characters/{character_id}/avatar")
async def api_upload_character_avatar(
    world_id: str,
    character_id: str,
    request: Request,
    file: UploadFile = File(...),
    next: str = Form(default=""),
) -> JSONResponse:
    app_factory, rt, card_svc = _character_card_service(world_id)
    try:
        data = await file.read()
        ext = _avatar_ext_from_filename(file.filename or "")
        card_svc.save_avatar_from_bytes(world_id, character_id, data, ext=ext)
        rt.session.commit()
        redirect_url = _resolve_avatar_redirect(next, world_id, character_id, request)
        return JSONResponse({"ok": True, "redirect_url": redirect_url})
    except DomainError as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=500)
    finally:
        rt.close()


@app.post("/worlds/{world_id}/characters/{character_id}/avatar")
async def upload_character_avatar(
    world_id: str,
    character_id: str,
    request: Request,
    file: UploadFile = File(...),
    next: str = Form(default=""),
) -> RedirectResponse:
    app_factory, rt, card_svc = _character_card_service(world_id)
    try:
        data = await file.read()
        ext = _avatar_ext_from_filename(file.filename or "")
        card_svc.save_avatar_from_bytes(world_id, character_id, data, ext=ext)
        rt.session.commit()
    finally:
        rt.close()
    url = _resolve_avatar_redirect(next, world_id, character_id, request)
    return RedirectResponse(url=url, status_code=303)


@app.post("/worlds/{world_id}/documents/upload")
async def upload_world_document(world_id: str, file: UploadFile = File(...)) -> RedirectResponse:
    ctx = _ctx()
    runtime = ctx.open()

    try:
        data = await file.read()
        runtime.documents.upload_world_document(
            world_id, file.filename or "document.txt", data, mime_type=file.content_type or ""
        )
        runtime.commit()
    finally:
        runtime.close()
    return RedirectResponse(url=f"/worlds/{world_id}", status_code=303)


@app.post("/worlds/{world_id}/documents/{doc_id}/delete")
def delete_world_document(world_id: str, doc_id: str) -> RedirectResponse:
    ctx = _ctx()
    runtime = ctx.open()

    try:
        runtime.documents.delete_world_document(doc_id)
        runtime.commit()
    finally:
        runtime.close()
    return RedirectResponse(url=f"/worlds/{world_id}", status_code=303)


@app.post("/worlds/{world_id}/state/set")
def set_state(
    world_id: str,
    scope: str = Form(default="world"),
    scope_id: str = Form(default=""),
    key: str = Form(...),
    value_json: str = Form(default=""),
) -> RedirectResponse:
    app_factory = _world_app()
    rt = app_factory.open_world(WorldId(world_id))
    try:
        value: Any = "" if value_json.strip() == "" else _json_loads_maybe(value_json, default="")
        character_id = CharacterId(scope_id) if scope == "character" and scope_id.strip() else None
        rt.state.set_value(
            WorldId(world_id), key, value, scope=scope, scope_id=character_id  # type: ignore[arg-type]
        )
        rt.session.commit()
    finally:
        rt.close()
    return RedirectResponse(url=f"/worlds/{world_id}", status_code=303)


@app.post("/worlds/{world_id}/events/record")
def record_event(
    world_id: str,
    event_type: str = Form(...),
    payload_json: str = Form(default="{}"),
    actor_id: str = Form(default=""),
    world_time: str = Form(default=""),
) -> RedirectResponse:
    app_factory = _world_app()
    rt = app_factory.open_world(WorldId(world_id))
    try:
        payload = _json_loads_maybe(payload_json, default={})
        actor = CharacterId(actor_id) if actor_id.strip() else None
        rt.event.record(
            WorldId(world_id),
            event_type,
            payload=payload,
            actor_id=actor,
            world_time=world_time.strip() or None,
        )
        rt.session.commit()
    finally:
        rt.close()
    return RedirectResponse(url=f"/worlds/{world_id}", status_code=303)


@app.post("/worlds/{world_id}/saves/create")
def create_save(
    world_id: str,
    slot_index: int = Form(...),
    label: str = Form(default=""),
) -> RedirectResponse:
    app_factory = _world_app()
    rt = app_factory.open_world(WorldId(world_id))
    try:
        rt.save.create_save(WorldId(world_id), slot_index, label=label)
        rt.session.commit()
    finally:
        rt.close()
    return RedirectResponse(url=f"/worlds/{world_id}", status_code=303)


@app.post("/worlds/{world_id}/saves/load")
def load_save(world_id: str, save_id: str = Form(...)) -> RedirectResponse:
    app_factory = _world_app()
    rt = app_factory.open_world(WorldId(world_id))
    try:
        rt.save.load_save(SaveId(save_id))
        rt.session.commit()
    finally:
        rt.close()
    return RedirectResponse(url=f"/worlds/{world_id}", status_code=303)


# ---------- Lorebook ----------


@app.post("/worlds/{world_id}/lore/create")
def create_lore_entry(
    world_id: str,
    scope: str = Form(default="world"),
    character_id: str = Form(default=""),
    keys: str = Form(default=""),
    content: str = Form(...),
    constant: str = Form(default=""),
    selective: str = Form(default="1"),
    recursive: str = Form(default=""),
    priority: int = Form(default=0),
    insertion_order: int = Form(default=0),
    position: str = Form(default="before_main"),
    depth: int = Form(default=4),
    enabled: str = Form(default="1"),
    comment: str = Form(default=""),
    probability: float = Form(default=1.0),
    lore_group: str = Form(default=""),
    group_override: str = Form(default=""),
    group_weight: int = Form(default=0),
    cooldown: int = Form(default=0),
    sticky: int = Form(default=0),
    character_filter: str = Form(default=""),
    filter_type: str = Form(default="include"),
    scan_depth: int = Form(default=0),
    use_group_scoring: str = Form(default=""),
) -> RedirectResponse:
    app_factory = _world_app()
    rt = app_factory.open_world(WorldId(world_id))
    try:
        entry = _lore_entry_from_form(
            scope=scope,
            character_id=character_id,
            keys=keys,
            content=content,
            constant=constant,
            selective=selective,
            recursive=recursive,
            priority=str(priority),
            insertion_order=str(insertion_order),
            position=position,
            depth=str(depth),
            enabled=enabled,
            comment=comment,
            probability=str(probability),
            lore_group=lore_group,
            group_override=group_override,
            group_weight=str(group_weight),
            cooldown=str(cooldown),
            sticky=str(sticky),
            character_filter=character_filter,
            filter_type=filter_type,
            scan_depth=str(scan_depth),
            use_group_scoring=use_group_scoring,
        )
        if entry is not None:
            rt.lore.save(entry)
            rt.session.commit()
    finally:
        rt.close()
    return RedirectResponse(url=f"/worlds/{world_id}?tab=lore", status_code=303)


@app.post("/worlds/{world_id}/lore/{entry_id}/update")
def update_lore_entry(
    world_id: str,
    entry_id: str,
    scope: str = Form(default="world"),
    character_id: str = Form(default=""),
    keys: str = Form(default=""),
    content: str = Form(...),
    constant: str = Form(default=""),
    selective: str = Form(default="1"),
    recursive: str = Form(default=""),
    priority: int = Form(default=0),
    insertion_order: int = Form(default=0),
    position: str = Form(default="before_main"),
    depth: int = Form(default=4),
    enabled: str = Form(default="1"),
    comment: str = Form(default=""),
    probability: float = Form(default=1.0),
    lore_group: str = Form(default=""),
    group_override: str = Form(default=""),
    group_weight: int = Form(default=0),
    cooldown: int = Form(default=0),
    sticky: int = Form(default=0),
    character_filter: str = Form(default=""),
    filter_type: str = Form(default="include"),
    scan_depth: int = Form(default=0),
    use_group_scoring: str = Form(default=""),
) -> RedirectResponse:
    from novel_world.core.domain.timestamps import utc_now

    app_factory = _world_app()
    rt = app_factory.open_world(WorldId(world_id))
    try:
        entry = rt.lore.get(entry_id)
        if entry.source == "character_book":
            return RedirectResponse(url=f"/worlds/{world_id}?tab=lore", status_code=303)
        entry.scope = scope if scope in ("world", "character") else "world"
        entry.character_id = character_id.strip()
        entry.keys = _parse_keys_field(keys)
        entry.content = content.strip()
        entry.constant = bool(constant)
        entry.selective = selective != "0"
        entry.recursive = bool(recursive)
        entry.priority = priority
        entry.insertion_order = insertion_order
        entry.position = position or "before_main"
        entry.depth = depth
        entry.enabled = enabled != "0"
        entry.comment = comment.strip()
        advanced = _lore_advanced_from_form(
            probability=str(probability),
            lore_group=lore_group,
            group_override=group_override,
            group_weight=str(group_weight),
            cooldown=str(cooldown),
            sticky=str(sticky),
            character_filter=character_filter,
            filter_type=filter_type,
            scan_depth=str(scan_depth),
            use_group_scoring=use_group_scoring,
        )
        for key, value in advanced.items():
            setattr(entry, key, value)
        entry.updated_at = utc_now()
        rt.lore.save(entry)
        rt.session.commit()
    finally:
        rt.close()
    return RedirectResponse(url=f"/worlds/{world_id}?tab=lore", status_code=303)


@app.post("/worlds/{world_id}/lore/{entry_id}/delete")
def delete_lore_entry(world_id: str, entry_id: str) -> RedirectResponse:
    app_factory = _world_app()
    rt = app_factory.open_world(WorldId(world_id))
    try:
        entry = rt.lore.get(entry_id)
        if entry.source != "character_book":
            rt.lore.delete(entry_id)
            rt.session.commit()
    finally:
        rt.close()
    return RedirectResponse(url=f"/worlds/{world_id}?tab=lore", status_code=303)


@app.post("/worlds/{world_id}/lore/import-st")
async def import_st_world_info_route(
    world_id: str,
    file: UploadFile = File(...),
    scope: str = Form(default="world"),
    character_id: str = Form(default=""),
    mode: str = Form(default="merge"),
) -> RedirectResponse:
    data = await file.read()
    app_factory = _world_app()
    rt = app_factory.open_world(WorldId(world_id))
    ctx = _ctx()
    runtime = ctx.open()
    count = 0
    try:
        count = rt.lore.import_st_world_info(
            data,
            scope=scope or "world",
            character_id=character_id or "",
            mode=mode or "merge",
        )
        rt.session.commit()
        runtime.chat.clear_world_cache(world_id)
        runtime.commit()
    finally:
        rt.close()
        runtime.close()
    return RedirectResponse(url=f"/worlds/{world_id}?tab=lore&imported={count}", status_code=303)


@app.get("/api/worlds/{world_id}/lore/export-st")
def export_st_world_info_route(
    world_id: str,
    scope: str = "",
    character_id: str = "",
) -> JSONResponse:
    app_factory = _world_app()
    rt = app_factory.open_world(WorldId(world_id))
    try:
        payload = rt.lore.export_st_world_info(
            scope=scope or None,
            character_id=character_id or None,
        )
    finally:
        rt.close()
    return JSONResponse(
        content=payload,
        headers={
            "Content-Disposition": f'attachment; filename="world_info_{world_id}.json"'
        },
        media_type="application/json",
    )


@app.get("/api/worlds/{world_id}/lore")
def api_list_lore(world_id: str) -> JSONResponse:
    app_factory = _world_app()
    rt = app_factory.open_world(WorldId(world_id))
    try:
        entries = rt.lore.list_entries(include_disabled=True)
        data = [
            {
                "id": e.id,
                "scope": e.scope,
                "character_id": e.character_id,
                "keys": e.keys,
                "content": e.content,
                "constant": e.constant,
                "selective": e.selective,
                "recursive": e.recursive,
                "priority": e.priority,
                "insertion_order": e.insertion_order,
                "position": e.position,
                "depth": e.depth,
                "enabled": e.enabled,
                "comment": e.comment,
                "source": e.source,
            }
            for e in entries
        ]
    finally:
        rt.close()
    return JSONResponse({"entries": data})


# ---------- Session prompt / config / memory / message ops ----------


@app.post("/api/sessions/{session_id}/background", response_model=None)
async def upload_session_background(
    request: Request,
    session_id: str,
    file: UploadFile | None = File(default=None),
    clear: str = Form(default=""),
) -> JSONResponse | RedirectResponse:
    ctx = _ctx()
    runtime = ctx.open()
    try:
        session = runtime.chat.get_session(session_id)
        svc = _session_service(runtime, session)
        config = dict(session.config or {})
        if clear.strip().lower() in ("1", "true", "on", "yes"):
            old = str(config.pop("background", "") or "").strip()
            if old:
                old_path = runtime.background.resolve_path(old)
                if old_path:
                    old_path.unlink(missing_ok=True)
        elif file and file.filename:
            data = await file.read()
            rel = runtime.background.save_session_background(session_id, data, file.filename)
            config["background"] = rel
        else:
            return JSONResponse({"ok": False, "message": "未选择文件"}, status_code=400)
        svc.update_session_config(session_id, {"background": config.get("background", "")})
        runtime.commit()
    except Exception as e:
        runtime.rollback()
        return JSONResponse({"ok": False, "message": str(e)}, status_code=400)
    finally:
        runtime.close()

    accept = request.headers.get("accept", "")
    if "application/json" in accept or request.headers.get("x-requested-with") == "fetch":
        return JSONResponse({"ok": True})
    return RedirectResponse(url=request.headers.get("referer", "/chat"), status_code=303)


@app.post("/api/worlds/{world_id}/background", response_model=None)
async def upload_world_background(
    request: Request,
    world_id: str,
    file: UploadFile | None = File(default=None),
    clear: str = Form(default=""),
) -> RedirectResponse | JSONResponse:
    ctx = _ctx()
    runtime = ctx.open()
    app_factory = _world_app()
    rt = app_factory.open_world(WorldId(world_id))
    try:
        world = rt.world.get(WorldId(world_id))
        settings = dict(world.settings or {}) if isinstance(world.settings, dict) else {}
        if clear.strip().lower() in ("1", "true", "on", "yes"):
            old = str(settings.pop("background", "") or "").strip()
            if old:
                old_path = runtime.background.resolve_path(old)
                if old_path:
                    old_path.unlink(missing_ok=True)
        elif file and file.filename:
            data = await file.read()
            rel = runtime.background.save_world_background(world_id, data, file.filename)
            settings["background"] = rel
        else:
            return JSONResponse({"ok": False, "message": "未选择文件"}, status_code=400)
        rt.world.update(
            WorldId(world_id),
            name=world.name,
            description=world.description,
            genre=world.genre,
            rules=world.rules,
            settings=settings,
        )
        rt.session.commit()
    except Exception as e:
        rt.session.rollback()
        return JSONResponse({"ok": False, "message": str(e)}, status_code=400)
    finally:
        rt.close()
        runtime.close()

    return RedirectResponse(url=request.headers.get("referer", f"/worlds/{world_id}"), status_code=303)


@app.get("/api/uploads/{file_path:path}")
def serve_upload(file_path: str):
    ctx = _ctx()
    runtime = ctx.open()
    try:
        path = runtime.background.resolve_path(file_path)
        if path is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="文件不存在")
        media = "application/octet-stream"
        suffix = path.suffix.lower()
        if suffix in (".jpg", ".jpeg"):
            media = "image/jpeg"
        elif suffix == ".png":
            media = "image/png"
        elif suffix == ".webp":
            media = "image/webp"
        elif suffix == ".gif":
            media = "image/gif"
        return FileResponse(path, media_type=media)
    finally:
        runtime.close()


@app.get("/api/worlds/{world_id}/export-pack")
def export_world_pack(world_id: str, include_uploads: str = "1"):
    ctx = _ctx()
    runtime = ctx.open()
    try:
        data = runtime.world_pack.export_world(
            world_id, include_uploads=include_uploads.strip() not in ("0", "false", "no")
        )
    except Exception as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=400)
    finally:
        runtime.close()
    filename = f"{world_id}.nworld.zip"
    return StreamingResponse(
        iter([data]),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/worlds/import-pack")
async def import_world_pack(file: UploadFile = File(...)) -> RedirectResponse:
    data = await file.read()
    ctx = _ctx()
    runtime = ctx.open()
    try:
        result = runtime.world_pack.import_world(data)
        runtime.commit()
        world_id = result["world_id"]
    except Exception:
        runtime.rollback()
        return RedirectResponse(url="/worlds?import_error=1", status_code=303)
    finally:
        runtime.close()
    return RedirectResponse(url=f"/worlds/{world_id}", status_code=303)


@app.get("/api/sessions/{session_id}/prompt-preview")
def prompt_preview_api(session_id: str, content: str = "") -> JSONResponse:
    ctx = _ctx()
    runtime = ctx.open()
    try:
        data = _preview_prompt(runtime, session_id, content)
    finally:
        runtime.close()
    return JSONResponse(data)


@app.get("/api/sessions/{session_id}/lore")
def list_session_lore_api(session_id: str) -> JSONResponse:
    from novel_world.modules.ai.services.session_lore_service import SessionLoreService

    ctx = _ctx()
    runtime = ctx.open()
    try:
        session = runtime.chat.get_session(session_id)
        entries = [e.to_dict() for e in SessionLoreService.list_entries(session)]
        return JSONResponse({"ok": True, "entries": entries})
    finally:
        runtime.close()


@app.post("/api/sessions/{session_id}/lore")
async def create_session_lore_api(session_id: str, request: Request) -> JSONResponse:
    from novel_world.modules.ai.services.session_lore_service import SessionLoreService

    body = await request.json()
    if not isinstance(body, dict):
        body = {}
    ctx = _ctx()
    runtime = ctx.open()
    try:
        session = runtime.chat.get_session(session_id)
        session, entry = SessionLoreService.create_entry(session, body)
        _update_session_config(runtime, session_id, {"session_lore": session.config.get("session_lore")})
        runtime.commit()
        return JSONResponse({"ok": True, "entry": entry.to_dict()})
    except Exception as e:
        runtime.rollback()
        return JSONResponse({"ok": False, "message": str(e)}, status_code=400)
    finally:
        runtime.close()


@app.post("/api/sessions/{session_id}/lore/{entry_id}")
async def update_session_lore_api(session_id: str, entry_id: str, request: Request) -> JSONResponse:
    from novel_world.modules.ai.services.session_lore_service import SessionLoreService

    body = await request.json()
    if not isinstance(body, dict):
        body = {}
    ctx = _ctx()
    runtime = ctx.open()
    try:
        session = runtime.chat.get_session(session_id)
        session = SessionLoreService.update_entry(session, entry_id, body)
        _update_session_config(runtime, session_id, {"session_lore": session.config.get("session_lore")})
        runtime.commit()
        return JSONResponse({"ok": True})
    except Exception as e:
        runtime.rollback()
        return JSONResponse({"ok": False, "message": str(e)}, status_code=400)
    finally:
        runtime.close()


@app.delete("/api/sessions/{session_id}/lore/{entry_id}")
def delete_session_lore_api(session_id: str, entry_id: str) -> JSONResponse:
    from novel_world.modules.ai.services.session_lore_service import SessionLoreService

    ctx = _ctx()
    runtime = ctx.open()
    try:
        session = runtime.chat.get_session(session_id)
        session = SessionLoreService.delete_entry(session, entry_id)
        _update_session_config(runtime, session_id, {"session_lore": session.config.get("session_lore")})
        runtime.commit()
        return JSONResponse({"ok": True})
    except Exception as e:
        runtime.rollback()
        return JSONResponse({"ok": False, "message": str(e)}, status_code=400)
    finally:
        runtime.close()


@app.post("/api/sessions/{session_id}/lore/import-st")
async def import_session_lore_st(session_id: str, file: UploadFile = File(...)) -> JSONResponse:
    from novel_world.modules.ai.services.session_lore_service import SessionLoreService

    data = await file.read()
    ctx = _ctx()
    runtime = ctx.open()
    try:
        session = runtime.chat.get_session(session_id)
        session, count = SessionLoreService.import_st(session, data, mode="merge")
        _update_session_config(runtime, session_id, {"session_lore": session.config.get("session_lore")})
        runtime.commit()
        return JSONResponse({"ok": True, "imported": count, "entries": [e.to_dict() for e in SessionLoreService.list_entries(session)]})
    except Exception as e:
        runtime.rollback()
        return JSONResponse({"ok": False, "message": str(e)}, status_code=400)
    finally:
        runtime.close()


@app.get("/api/sessions/{session_id}/lore/export-st")
def export_session_lore_st(session_id: str) -> JSONResponse:
    from novel_world.modules.ai.services.session_lore_service import SessionLoreService

    ctx = _ctx()
    runtime = ctx.open()
    try:
        session = runtime.chat.get_session(session_id)
        return JSONResponse(SessionLoreService.export_st(session))
    finally:
        runtime.close()


@app.post("/settings/import-regex")
async def import_st_regex_settings(file: UploadFile = File(...)) -> RedirectResponse:
    from novel_world.modules.ai.services.st_regex_codec import parse_st_regex_scripts

    data = await file.read()
    scripts = parse_st_regex_scripts(data)
    runtime = _ctx().open()
    try:
        existing = get_user_prefs(runtime.session.connection)
        merged = dict(existing)
        merged["global_regex_scripts"] = [s.to_dict() for s in scripts]
        save_user_prefs(runtime.session.connection, merged)
        runtime.commit()
    finally:
        runtime.close()
    return RedirectResponse(url="/settings", status_code=303)


@app.get("/api/sessions/{session_id}/branches")
def list_message_branches(session_id: str) -> JSONResponse:
    ctx = _ctx()
    runtime = ctx.open()
    try:
        branches = runtime.message_ops.list_branches(session_id)
        return JSONResponse({"ok": True, "branches": branches})
    finally:
        runtime.close()


@app.post("/settings/import-stscript")
async def import_stscript_settings(file: UploadFile = File(...)) -> RedirectResponse:
    from novel_world.modules.stscript.engine import parse_st_scripts_json

    data = await file.read()
    scripts = parse_st_scripts_json(data)
    runtime = _ctx().open()
    try:
        existing = get_user_prefs(runtime.session.connection)
        merged = dict(existing)
        merged["global_stscripts"] = [
            {"name": s.name, "content": s.content, "triggers": s.triggers, "enabled": s.enabled}
            for s in scripts
        ]
        save_user_prefs(runtime.session.connection, merged)
        runtime.commit()
    finally:
        runtime.close()
    return RedirectResponse(url="/settings", status_code=303)


@app.post("/api/worlds/{world_id}/data-bank/index")
async def index_data_bank(world_id: str, request: Request) -> JSONResponse:
    body = await request.json()
    title = str(body.get("title") or "资料")
    content = str(body.get("content") or "")
    app_factory = _world_app()
    rt = app_factory.open_world(WorldId(world_id))
    try:
        from novel_world.modules.world.services.data_bank_service import DataBankService

        count = DataBankService(rt.session.connection).index_text(
            world_id=world_id, title=title, content=content
        )
        rt.session.commit()
        return JSONResponse({"ok": True, "chunks": count})
    except Exception as e:
        rt.session.rollback()
        return JSONResponse({"ok": False, "message": str(e)}, status_code=400)
    finally:
        rt.close()


@app.get("/api/worlds/{world_id}/data-bank")
def list_data_bank(world_id: str) -> JSONResponse:
    app_factory = _world_app()
    rt = app_factory.open_world(WorldId(world_id))
    try:
        from novel_world.modules.world.services.data_bank_service import DataBankService

        rows = DataBankService(rt.session.connection).list_chunks(world_id)
        return JSONResponse({"ok": True, "chunks": rows})
    finally:
        rt.close()


def _resolve_tts_request_voice(
    body: dict,
    prefs: dict,
    *,
    world_id: str = "",
    character_id: str = "",
) -> str:
    from novel_world.core.domain.ids import CharacterId, WorldId
    from novel_world.modules.ai.services.tts_voice_resolver import (
        DEFAULT_EDGE_VOICE,
        resolve_voice_for_character,
    )

    explicit = str(body.get("voice") or "").strip()
    if explicit:
        return explicit
    from novel_world.modules.ai.providers.tts_registry import normalize_tts_backend

    global_default = str(prefs.get("tts_voice") or "").strip()
    backend = normalize_tts_backend(str(prefs.get("tts_backend") or "edge"))
    if character_id and world_id:
        app_factory = _world_app()
        rt = app_factory.open_world(WorldId(world_id))
        try:
            character = rt.character.get(CharacterId(character_id))
            return resolve_voice_for_character(character, global_default=global_default)
        except Exception:
            pass
        finally:
            rt.close()
    if global_default:
        return global_default
    if backend == "openai_compatible":
        return str(prefs.get("tts_openai_voice") or "alloy")
    return DEFAULT_EDGE_VOICE


@app.get("/api/tts/voices")
async def tts_voices_api(request: Request, backend: str = "edge", locale: str = "") -> JSONResponse:
    from novel_world.infrastructure.user_preferences import get_user_prefs
    from novel_world.modules.ai.providers.tts_registry import build_tts_provider, normalize_tts_backend

    runtime = _ctx().open()
    try:
        prefs = get_user_prefs(runtime.session.connection)
        backend_name = normalize_tts_backend(backend or prefs.get("tts_backend") or "edge")
        locale_prefix = (locale or ("zh" if str(prefs.get("locale") or "zh").startswith("zh") else "en")).strip()
        if backend_name == "browser":
            voices = []
        else:
            query_prefs = {**prefs, "tts_backend": backend_name}
            provider = build_tts_provider(query_prefs, require_credentials=False)
            voices = provider.list_voices(locale_prefix=locale_prefix) if provider else []
    finally:
        runtime.close()
    return JSONResponse({"ok": True, "backend": backend_name, "voices": voices})


def _synthesize_tts_audio(body: dict, prefs: dict) -> tuple[bytes | None, str | None, str]:
    from novel_world.modules.ai.providers.tts_registry import build_tts_provider, normalize_tts_backend

    text = str(body.get("text") or "")
    backend = normalize_tts_backend(str(prefs.get("tts_backend") or "edge"))
    if backend == "browser":
        return None, "browser backend uses client speechSynthesis", "audio/mpeg"
    try:
        rate = float(body.get("rate") or prefs.get("tts_rate") or 1.0)
    except (TypeError, ValueError):
        rate = 1.0
    voice = _resolve_tts_request_voice(
        body,
        prefs,
        world_id=str(body.get("world_id") or ""),
        character_id=str(body.get("character_id") or ""),
    )
    provider = build_tts_provider(prefs)
    if provider is None:
        return None, "TTS 后端未配置", "audio/mpeg"
    if backend == "openai_compatible":
        voice = voice or str(prefs.get("tts_openai_voice") or "alloy")
    audio = provider.synthesize(text, voice=voice, rate=rate)
    media_type = provider.media_type()
    if not audio:
        return None, "TTS 合成失败或未安装 edge-tts", media_type
    return audio, None, media_type


@app.post("/api/tts/speak")
async def tts_speak_api(request: Request):
    from fastapi.responses import Response

    from novel_world.infrastructure.user_preferences import get_user_prefs

    body = await request.json()
    runtime = _ctx().open()
    try:
        prefs = get_user_prefs(runtime.session.connection)
        audio, err, media_type = _synthesize_tts_audio(body, prefs)
    finally:
        runtime.close()
    if err:
        return JSONResponse({"ok": False, "message": err}, status_code=400)
    return Response(content=audio, media_type=media_type)


@app.post("/api/tts/preview")
async def tts_preview_api(request: Request):
    from fastapi.responses import Response

    from novel_world.infrastructure.user_preferences import get_user_prefs

    body = await request.json()
    if not str(body.get("text") or "").strip():
        body = {**body, "text": "你好，这是音色试听。"}
    runtime = _ctx().open()
    try:
        prefs = get_user_prefs(runtime.session.connection)
        audio, err, media_type = _synthesize_tts_audio(body, prefs)
    finally:
        runtime.close()
    if err:
        return JSONResponse({"ok": False, "message": err}, status_code=400)
    return Response(content=audio, media_type=media_type)


@app.post("/api/sd/txt2img")
async def sd_txt2img_api(request: Request) -> JSONResponse:
    from novel_world.infrastructure.user_preferences import get_user_prefs
    from novel_world.modules.ai.providers.sd_webui_provider import SDWebUIProvider

    body = await request.json()
    prompt = str(body.get("prompt") or "")
    runtime = _ctx().open()
    try:
        prefs = get_user_prefs(runtime.session.connection)
        provider = SDWebUIProvider(base_url=str(prefs.get("sd_webui_url") or "http://127.0.0.1:7860"))
        import base64

        img = provider.txt2img(prompt)
        if not img:
            return JSONResponse({"ok": False, "message": "SD WebUI 未返回图像"}, status_code=400)
        return JSONResponse({"ok": True, "image_b64": base64.b64encode(img).decode("ascii")})
    except Exception as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=400)
    finally:
        runtime.close()


@app.get("/api/settings/regex/export")
def export_st_regex_settings() -> JSONResponse:
    from novel_world.modules.ai.services.st_regex_codec import export_st_regex_scripts
    from novel_world.modules.ai.domain.regex_script import RegexScript

    runtime = _ctx().open()
    try:
        prefs = get_user_prefs(runtime.session.connection)
        scripts = [
            RegexScript.from_dict(item, script_id=str(item.get("id", "")))
            for item in (prefs.get("global_regex_scripts") or [])
            if isinstance(item, dict)
        ]
        return JSONResponse(export_st_regex_scripts(scripts))
    finally:
        runtime.close()


@app.post("/api/sessions/{session_id}/import-preset")
async def import_st_preset_session(session_id: str, file: UploadFile = File(...)) -> JSONResponse:
    from novel_world.modules.ai.services.st_preset_codec import parse_st_preset

    data = await file.read()
    preset = parse_st_preset(data)
    patch: dict[str, Any] = {}
    if preset.get("generation"):
        patch["generation"] = preset["generation"]
    if preset.get("prompt_layers"):
        patch["prompt_layers"] = preset["prompt_layers"]
    if preset.get("prompt_profile"):
        patch["prompt_profile"] = preset["prompt_profile"]
    ctx = _ctx()
    runtime = ctx.open()
    try:
        session = _update_session_config(runtime, session_id, patch)
        runtime.commit()
        return JSONResponse({"ok": True, "config": session.config, "name": preset.get("name", "")})
    except Exception as e:
        runtime.rollback()
        return JSONResponse({"ok": False, "message": str(e)}, status_code=400)
    finally:
        runtime.close()


@app.post("/api/sessions/{session_id}/config")
async def update_session_config_api(request: Request, session_id: str) -> JSONResponse:
    body = await request.json()
    if not isinstance(body, dict):
        body = {}
    ctx = _ctx()
    runtime = ctx.open()
    try:
        session = _update_session_config(runtime, session_id, body)
        runtime.commit()
        return JSONResponse({"ok": True, "config": session.config})
    except Exception as e:
        runtime.rollback()
        return JSONResponse({"ok": False, "message": str(e)}, status_code=400)
    finally:
        runtime.close()


@app.get("/api/sessions/{session_id}/memories")
def list_memories_api(session_id: str) -> JSONResponse:
    ctx = _ctx()
    runtime = ctx.open()
    try:
        items = runtime.memory.list(session_id)
        data = [
            {
                "id": m.id,
                "content": m.content,
                "keywords": m.keywords,
                "pinned": m.pinned,
                "source_message_id": m.source_message_id,
            }
            for m in items
        ]
    finally:
        runtime.close()
    return JSONResponse({"memories": data})


@app.post("/api/sessions/{session_id}/memories")
def pin_memory_api(
    session_id: str,
    content: str = Form(...),
    keywords: str = Form(default=""),
    pinned: str = Form(default="1"),
    message_id: str = Form(default=""),
) -> JSONResponse:
    ctx = _ctx()
    runtime = ctx.open()
    try:
        mem = runtime.memory.pin(
            session_id,
            content,
            keywords=_parse_keys_field(keywords),
            message_id=message_id,
            pinned=pinned != "0",
        )
        runtime.commit()
        return JSONResponse(
            {
                "ok": True,
                "memory": {
                    "id": mem.id,
                    "content": mem.content,
                    "keywords": mem.keywords,
                    "pinned": mem.pinned,
                },
            }
        )
    except Exception as e:
        runtime.rollback()
        return JSONResponse({"ok": False, "message": str(e)}, status_code=400)
    finally:
        runtime.close()


@app.post("/api/sessions/{session_id}/memories/{memory_id}/pin")
def set_memory_pinned_api(
    session_id: str,
    memory_id: str,
    pinned: str = Form(default="1"),
) -> JSONResponse:
    ctx = _ctx()
    runtime = ctx.open()
    try:
        mem = runtime.memory.set_pinned(memory_id, pinned=pinned != "0")
        if mem.session_id != session_id:
            from novel_world.core.exceptions import NotFoundError

            raise NotFoundError("记忆不属于该会话")
        runtime.commit()
        return JSONResponse(
            {
                "ok": True,
                "memory": {
                    "id": mem.id,
                    "content": mem.content,
                    "keywords": mem.keywords,
                    "pinned": mem.pinned,
                },
            }
        )
    except Exception as e:
        runtime.rollback()
        return JSONResponse({"ok": False, "message": str(e)}, status_code=400)
    finally:
        runtime.close()


@app.post("/api/sessions/{session_id}/memories/{memory_id}/delete")
def delete_memory_api(session_id: str, memory_id: str) -> JSONResponse:
    ctx = _ctx()
    runtime = ctx.open()
    try:
        runtime.memory.delete(memory_id)
        runtime.commit()
        return JSONResponse({"ok": True})
    except Exception as e:
        runtime.rollback()
        return JSONResponse({"ok": False, "message": str(e)}, status_code=400)
    finally:
        runtime.close()


@app.post("/api/sessions/{session_id}/messages/{message_id}/regenerate")
async def regenerate_message_api(
    session_id: str,
    message_id: str,
    swipe: str = Form(default=""),
) -> StreamingResponse:
    def event_generator():
        ctx = _ctx()
        runtime = ctx.open()
        try:
            gen = runtime.message_ops.regenerate(
                session_id, message_id, swipe=swipe == "1"
            )
            for chunk in gen:
                if isinstance(chunk, dict):
                    payload = json.dumps(chunk.get("data", chunk), ensure_ascii=False)
                    yield f"event: {chunk.get('event', 'message')}\ndata: {payload}\n\n"
                else:
                    payload = json.dumps({"kind": chunk.kind, "text": chunk.text}, ensure_ascii=False)
                    yield f"event: {chunk.kind}\ndata: {payload}\n\n"
            runtime.commit()
        except Exception as e:
            runtime.rollback()
            err = json.dumps({"kind": "error", "text": str(e)}, ensure_ascii=False)
            yield f"event: error\ndata: {err}\n\n"
        finally:
            runtime.close()

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/api/sessions/{session_id}/messages/{message_id}/edit", response_model=None)
def edit_message_api(
    session_id: str,
    message_id: str,
    content: str = Form(...),
    regenerate_after: str = Form(default=""),
    fork: str = Form(default=""),
):
    if regenerate_after == "1":
        def event_generator():
            ctx = _ctx()
            runtime = ctx.open()
            try:
                runtime.message_ops.edit(
                    session_id, message_id, content, regenerate_after=True
                )
                for chunk in runtime.message_ops.stream_after_edit(session_id):
                    if isinstance(chunk, dict):
                        payload = json.dumps(chunk.get("data", chunk), ensure_ascii=False)
                        yield f"event: {chunk.get('event', 'message')}\ndata: {payload}\n\n"
                    else:
                        payload = json.dumps({"kind": chunk.kind, "text": chunk.text}, ensure_ascii=False)
                        yield f"event: {chunk.kind}\ndata: {payload}\n\n"
                runtime.commit()
            except Exception as e:
                runtime.rollback()
                err = json.dumps({"kind": "error", "text": str(e)}, ensure_ascii=False)
                yield f"event: error\ndata: {err}\n\n"
            finally:
                runtime.close()

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    ctx = _ctx()
    runtime = ctx.open()
    try:
        msg = runtime.message_ops.edit(
            session_id, message_id, content, fork=fork == "1"
        )
        runtime.commit()
        return JSONResponse(
            {
                "ok": True,
                "forked": fork == "1",
                "message": {
                    "id": msg.id,
                    "content": msg.content,
                    "role": msg.role,
                    "parent_id": msg.parent_id,
                },
            }
        )
    except Exception as e:
        runtime.rollback()
        return JSONResponse({"ok": False, "message": str(e)}, status_code=400)
    finally:
        runtime.close()


@app.post("/api/sessions/{session_id}/messages/{message_id}/delete")
def delete_message_api(
    session_id: str,
    message_id: str,
    cascade: str = Form(default=""),
) -> JSONResponse:
    ctx = _ctx()
    runtime = ctx.open()
    try:
        runtime.message_ops.delete(session_id, message_id, cascade=cascade == "1")
        runtime.commit()
        return JSONResponse({"ok": True})
    except Exception as e:
        runtime.rollback()
        return JSONResponse({"ok": False, "message": str(e)}, status_code=400)
    finally:
        runtime.close()


@app.post("/api/sessions/{session_id}/messages/{message_id}/swipe")
def swipe_message_api(
    session_id: str,
    message_id: str,
    direction: str = Form(default="next"),
) -> JSONResponse:
    ctx = _ctx()
    runtime = ctx.open()
    try:
        msg = runtime.message_ops.swipe(session_id, message_id, direction=direction)
        runtime.commit()
        return JSONResponse(
            {
                "ok": True,
                "message": {
                    "id": msg.id,
                    "content": msg.content,
                    "thinking_content": msg.thinking_content,
                    "active_variant": msg.active_variant,
                    "variants_count": len(msg.variants),
                },
            }
        )
    except Exception as e:
        runtime.rollback()
        return JSONResponse({"ok": False, "message": str(e)}, status_code=400)
    finally:
        runtime.close()


@app.exception_handler(DomainError)
def domain_error_handler(request: Request, exc: DomainError) -> HTMLResponse:
    nav = _nav_context(request, active="")
    nav["message"] = str(exc)
    return templates.TemplateResponse(request, "error.html", nav, status_code=400)
