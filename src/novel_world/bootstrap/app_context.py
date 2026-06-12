from __future__ import annotations



from dataclasses import dataclass

from pathlib import Path



from novel_world.bootstrap.app_factory import create_app

from novel_world.bootstrap.config import AppConfig, default_config

from novel_world.infrastructure.db.app_session import AppDatabaseSession

from novel_world.infrastructure.repositories.sqlite_chat_repository import SqliteChatRepository

from novel_world.infrastructure.repositories.sqlite_provider_repository import SqliteProviderRepository

from novel_world.infrastructure.user_preferences import get_user_prefs

from novel_world.modules.ai.services.chat_service import ChatService

from novel_world.modules.ai.services.group_chat_service import GroupChatService

from novel_world.modules.ai.services.memory_service import MemoryService

from novel_world.modules.ai.services.message_ops_service import MessageOpsService

from novel_world.modules.ai.services.prompt_assembler import PromptAssembler

from novel_world.modules.ai.services.roleplay_service import RoleplayService

from novel_world.modules.ai.services.provider_registry import ProviderRegistry

from novel_world.modules.ai.services.command_parser import register_default_commands
from novel_world.modules.appearance.services.background_service import BackgroundService
from novel_world.modules.documents.services.document_service import DocumentService
from novel_world.modules.extensions.hook_bus import clear_hooks
from novel_world.modules.extensions.loader import load_extensions
from novel_world.modules.sync.providers.local_sync_provider import LocalSyncProvider
from novel_world.modules.world.services.world_pack_service import WorldPackService





def _session_defaults_from_prefs(prefs: dict) -> dict:

    return {

        "default_generation": dict(prefs.get("default_generation") or {}),

        "default_prompt_layers": dict(prefs.get("default_prompt_layers") or {}),

        "lore_token_budget": int(prefs.get("lore_token_budget") or 2000),

    }





@dataclass

class AppRuntime:

    config: AppConfig

    session: AppDatabaseSession

    providers: ProviderRegistry

    chat: ChatService

    documents: DocumentService

    group_chat: GroupChatService

    roleplay: RoleplayService

    memory: MemoryService

    message_ops: MessageOpsService

    prompt_assembler: PromptAssembler

    background: BackgroundService

    world_pack: WorldPackService

    sync: LocalSyncProvider

    extensions: list[dict]



    def commit(self) -> None:

        self.session.commit()



    def rollback(self) -> None:

        self.session.rollback()



    def close(self) -> None:

        self.session.close()





class AppContextFactory:

    def __init__(self, base_dir: Path | None = None) -> None:

        self.base_dir = base_dir

        self.config = default_config(base_dir)

        self.config.ensure_dirs()



    def open(self) -> AppRuntime:

        session = AppDatabaseSession(self.config.app_db_path)

        session.open()

        conn = session.connection

        prefs = get_user_prefs(conn)

        session_defaults = _session_defaults_from_prefs(prefs)

        provider_repo = SqliteProviderRepository(conn)

        chat_repo = SqliteChatRepository(conn)

        providers = ProviderRegistry(provider_repo)

        documents = DocumentService(self.config, conn)

        assembler = PromptAssembler()

        memory = MemoryService(chat_repo)

        world_app = create_app(self.base_dir)

        chat = ChatService(

            chat_repo,

            providers,

            world_app=world_app,

            base_dir=self.base_dir,

            documents=documents,

            memory_service=memory,

            prompt_assembler=assembler,

            default_session_config=session_defaults,

        )

        group_chat = GroupChatService(

            chat_repo,

            providers,

            world_app=world_app,

            base_dir=self.base_dir,

            memory_service=memory,

            prompt_assembler=assembler,

            default_session_config=session_defaults,

        )

        roleplay = RoleplayService(

            chat_repo,

            providers,

            world_app=world_app,

            base_dir=self.base_dir,

            config=self.config,

            memory_service=memory,

            prompt_assembler=assembler,

            default_session_config=session_defaults,

        )

        message_ops = MessageOpsService(chat_repo, roleplay, chat, group_chat)

        clear_hooks()
        register_default_commands()

        extensions = load_extensions(
            self.config.extensions_dir,
            disabled=list(prefs.get("disabled_extensions") or []),
            mods_dir=self.config.mods_dir,
            world_packs_dir=self.config.world_packs_dir,
        )

        return AppRuntime(

            config=self.config,

            session=session,

            providers=providers,

            chat=chat,

            documents=documents,

            group_chat=group_chat,

            roleplay=roleplay,

            memory=memory,

            message_ops=message_ops,

            prompt_assembler=assembler,

            background=BackgroundService(self.config),

            world_pack=WorldPackService(self.config, world_app),

            sync=LocalSyncProvider(self.config.world_packs_dir),

            extensions=extensions,

        )





def create_app_context(base_dir: Path | None = None) -> AppContextFactory:

    return AppContextFactory(base_dir)


