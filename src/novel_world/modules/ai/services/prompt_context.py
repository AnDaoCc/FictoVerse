from __future__ import annotations



from typing import Any



from novel_world.bootstrap.app_factory import AppFactory

from novel_world.core.domain.ids import WorldId

from novel_world.infrastructure.repositories.sqlite_lore_repository import SqliteLoreRepository

from novel_world.modules.ai.domain.entities import ChatSession

from novel_world.modules.ai.services.lore_engine import LoreEngine, LoreResult

from novel_world.modules.ai.services.lore_session_state import LoreSessionState

from novel_world.modules.world.domain.lore_entry import LoreEntry





def build_scan_text(
    messages,
    user_input: str = "",
    *,
    limit: int = 12,
    scan_depth: int = 0,
) -> str:
    effective = scan_depth if scan_depth > 0 else limit
    parts: list[str] = []
    for item in messages[-effective:]:
        text = getattr(item, "content", "") or ""
        if text.strip():
            parts.append(text.strip())
    if user_input.strip():
        parts.append(user_input.strip())
    return "\n".join(parts)


def build_scan_text_for_entry(
    messages,
    user_input: str,
    entry: LoreEntry,
    *,
    default_limit: int = 12,
) -> str:
    depth = entry.scan_depth if entry.scan_depth > 0 else default_limit
    return build_scan_text(messages, user_input, limit=default_limit, scan_depth=depth)





def merge_session_lore(

    world_entries: list[LoreEntry],

    session_config: dict[str, Any] | None,

) -> list[LoreEntry]:

    session_entries = LoreEngine.session_lore_from_config(session_config)

    if not session_entries:

        return world_entries

    seen = {e.id for e in world_entries}

    merged = list(world_entries)

    for entry in session_entries:

        if entry.id not in seen:

            merged.append(entry)

            seen.add(entry.id)

    return merged





def scan_lore_for_session(
    entries: list[LoreEntry],
    scan_text: str,
    session: ChatSession,
    *,
    token_budget: int = 2000,
    active_character_id: str = "",
    active_character_name: str = "",
    tick_user_turn: bool = True,
    messages: list | None = None,
    user_input: str = "",
    scan_limit: int = 12,
    vector_conn=None,
) -> tuple[LoreResult, LoreSessionState]:
    state = LoreSessionState.from_config(session.config)
    if tick_user_turn:
        state.tick_user_turn()
    world_id = str(session.world_id or "")
    if vector_conn is not None:
        from novel_world.modules.ai.services.hybrid_lore_engine import HybridLoreEngine

        engine = HybridLoreEngine(vector_conn)
        result = engine.scan(
            entries,
            scan_text,
            token_budget=token_budget,
            session_state=state,
            active_character_id=active_character_id,
            active_character_name=active_character_name,
            messages=messages,
            user_input=user_input,
            scan_limit=scan_limit,
            world_id=world_id,
        )
    else:
        engine = LoreEngine()
        result = engine.scan(
            entries,
            scan_text,
            token_budget=token_budget,
            session_state=state,
            active_character_id=active_character_id,
            active_character_name=active_character_name,
            messages=messages,
            user_input=user_input,
            scan_limit=scan_limit,
        )
    return result, state


def load_data_bank_context(
    conn,
    world_id: str,
    query: str,
    *,
    top_k: int = 5,
) -> str:
    if not world_id or not query.strip():
        return ""
    from novel_world.modules.world.services.data_bank_service import DataBankService

    hits = DataBankService(conn).search(world_id, query, top_k=top_k)
    if not hits:
        return ""
    return "【Data Bank】\n" + "\n\n".join(hits)





def persist_lore_state(session: ChatSession, state: LoreSessionState) -> ChatSession:

    config = dict(session.config or {})

    config.update(state.to_config_patch())

    session.config = config

    return session





def load_lore_entries(

    world_app: AppFactory,

    world_id: str,

    *,

    character_id: str | None = None,

    character_metadata: dict | None = None,

    extra_characters: list[tuple[str, dict | None]] | None = None,

    session_config: dict[str, Any] | None = None,

) -> list[LoreEntry]:

    """加载世界 DB lore + character_book + 会话 lore（合并去重）。"""

    engine = LoreEngine()

    rt = world_app.open_world(WorldId(world_id))

    try:

        repo = SqliteLoreRepository(rt.session.connection)

        db_entries = [

            e for e in repo.list_all_admin(character_id=character_id) if e.enabled

        ]

        book_entries: list[LoreEntry] = []

        if character_id and character_metadata is not None:

            card = (character_metadata or {}).get("card") or {}

            book_entries.extend(

                engine.entries_from_character_book(card.get("character_book"), character_id)

            )

        if extra_characters:

            for cid, meta in extra_characters:

                card = (meta or {}).get("card") or {}

                book_entries.extend(engine.entries_from_character_book(card.get("character_book"), cid))

        merged = engine.merge_entries(db_entries, book_entries)

        return merge_session_lore(merged, session_config)

    finally:

        rt.close()





def load_group_lore_entries(

    world_app: AppFactory,

    members: list[tuple[str, str, dict | None]],

    *,

    session_config: dict[str, Any] | None = None,

) -> list[LoreEntry]:

    """群聊：各成员世界的 world lore + 各成员 character_book + 会话 lore。"""

    engine = LoreEngine()

    merged: list[LoreEntry] = []

    seen: set[str] = set()

    by_world: dict[str, list[tuple[str, dict | None]]] = {}

    for world_id, character_id, meta in members:

        by_world.setdefault(world_id, []).append((character_id, meta))



    for world_id, chars in by_world.items():

        rt = world_app.open_world(WorldId(world_id))

        try:

            repo = SqliteLoreRepository(rt.session.connection)

            for entry in repo.list_all_admin():

                if not entry.enabled:

                    continue

                if entry.scope == "world" and entry.id not in seen:

                    merged.append(entry)

                    seen.add(entry.id)

            for character_id, meta in chars:

                db_char = [

                    e

                    for e in repo.list_all_admin(character_id=character_id)

                    if e.enabled and e.scope == "character"

                ]

                book = engine.entries_from_character_book(

                    ((meta or {}).get("card") or {}).get("character_book"), character_id

                )

                for entry in engine.merge_entries(db_char, book):

                    if entry.id not in seen:

                        merged.append(entry)

                        seen.add(entry.id)

        finally:

            rt.close()

    return merge_session_lore(merged, session_config)


