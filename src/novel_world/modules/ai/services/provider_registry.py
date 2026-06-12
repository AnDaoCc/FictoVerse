from __future__ import annotations

from novel_world.core.domain.timestamps import utc_now
from novel_world.core.exceptions import NotFoundError, ValidationError
from novel_world.modules.ai.domain.entities import (
    ChatMessage,
    ProviderConfig,
    ProviderId,
    ProviderType,
    new_provider_id,
)
from novel_world.modules.ai.catalog import get_preset
from novel_world.modules.ai.ports.llm_provider import LLMProvider, ProviderRepository
from novel_world.modules.ai.providers.anthropic_provider import AnthropicProvider
from novel_world.modules.ai.providers.gemini_provider import GeminiProvider
from novel_world.modules.ai.providers.openai_provider import OpenAICompatibleProvider, OpenAIProvider


class ProviderRegistry:
    def __init__(self, repository: ProviderRepository) -> None:
        self._repository = repository

    def list_all(self) -> list[ProviderConfig]:
        return self._repository.list_all()

    def list_enabled(self) -> list[ProviderConfig]:
        return self._repository.list_enabled()

    def find_by_catalog_slug(self, slug: str, *, enabled_only: bool = True) -> ProviderConfig | None:
        for provider in self._repository.list_all():
            if provider.config.get("catalog_slug") != slug:
                continue
            if enabled_only and not provider.enabled:
                continue
            return provider
        return None

    def resolve_provider_ref(self, provider_ref: str) -> ProviderId:
        if provider_ref.startswith("preset:"):
            slug = provider_ref.removeprefix("preset:")
            provider = self.find_by_catalog_slug(slug)
            if provider is None:
                raise ValidationError(f"请先在设置中配置该模型厂商：{slug}")
            return provider.id
        self.get(provider_ref)
        return provider_ref

    def get(self, provider_id: ProviderId) -> ProviderConfig:
        provider = self._repository.get(provider_id)
        if provider is None:
            raise NotFoundError(f"模型提供商不存在: {provider_id}")
        return provider

    def create(
        self,
        name: str,
        provider_type: ProviderType,
        config: dict,
        *,
        enabled: bool = True,
    ) -> ProviderConfig:
        if not name.strip():
            raise ValidationError("提供商名称不能为空。")
        now = utc_now()
        provider = ProviderConfig(
            id=new_provider_id(),
            name=name.strip(),
            type=provider_type,
            config=config,
            enabled=enabled,
            created_at=now,
            updated_at=now,
        )
        self._repository.save(provider)
        return provider

    def update(
        self,
        provider_id: ProviderId,
        *,
        name: str | None = None,
        config: dict | None = None,
        enabled: bool | None = None,
    ) -> ProviderConfig:
        provider = self.get(provider_id)
        if name is not None:
            provider.name = name.strip()
        if config is not None:
            provider.config = config
        if enabled is not None:
            provider.enabled = enabled
        provider.updated_at = utc_now()
        self._repository.save(provider)
        return provider

    def delete(self, provider_id: ProviderId) -> None:
        self.get(provider_id)
        self._repository.delete(provider_id)

    def build_client(self, provider_id: ProviderId) -> LLMProvider:
        provider = self.get(provider_id)
        if not provider.enabled:
            raise ValidationError(f"提供商已禁用: {provider.name}")
        cfg = provider.config
        if provider.type == "openai":
            return OpenAIProvider(
                api_key=cfg.get("api_key", ""),
                base_url=cfg.get("base_url", "https://api.openai.com/v1"),
            )
        if provider.type == "openai_compatible":
            return OpenAICompatibleProvider(
                api_key=cfg.get("api_key", ""),
                base_url=cfg.get("base_url", ""),
            )
        if provider.type == "anthropic":
            return AnthropicProvider(
                api_key=cfg.get("api_key", ""),
                base_url=cfg.get("base_url", "https://api.anthropic.com"),
            )
        if provider.type == "gemini":
            return GeminiProvider(
                api_key=cfg.get("api_key", ""),
                base_url=cfg.get("base_url", "https://generativelanguage.googleapis.com/v1beta"),
            )
        raise ValidationError(f"未知提供商类型: {provider.type}")

    def test_connection(self, provider_id: ProviderId, *, model: str | None = None) -> str:
        provider = self.get(provider_id)
        client = self.build_client(provider_id)
        preset = get_preset(str(provider.config.get("catalog_slug", "")))
        fallback_model = preset.default_model if preset else "gpt-4o-mini"
        test_model = model or provider.config.get("model") or fallback_model
        reply = client.complete(
            [ChatMessage(role="user", content="请回复：连接成功")],
            model=test_model,
        )
        return reply.strip()

    def list_available_models(self, provider_id: ProviderId) -> dict:
        provider = self.get(provider_id)
        configured_model = str(provider.config.get("model", "")).strip()
        preset = get_preset(str(provider.config.get("catalog_slug", "")))
        fallback_models = list(preset.models) if preset else ([configured_model] if configured_model else [])
        default_model = configured_model or (preset.default_model if preset else "")

        client = self.build_client(provider_id)
        list_fn = getattr(client, "list_models", None)
        if list_fn is not None:
            try:
                api_models = list_fn()
                if api_models:
                    preferred = default_model
                    if preferred and preferred not in api_models:
                        if preset and preset.default_model in api_models:
                            preferred = preset.default_model
                        else:
                            preferred = api_models[0]
                    elif not preferred:
                        preferred = api_models[0]
                    return {
                        "models": api_models,
                        "default_model": preferred,
                        "source": "api",
                    }
            except Exception as exc:
                return {
                    "models": fallback_models,
                    "default_model": default_model or (fallback_models[0] if fallback_models else ""),
                    "source": "catalog",
                    "error": str(exc),
                }

        return {
            "models": fallback_models,
            "default_model": default_model or (fallback_models[0] if fallback_models else ""),
            "source": "catalog",
        }

    @staticmethod
    def discover_models(provider_type: ProviderType, *, api_key: str, base_url: str) -> dict:
        if provider_type == "openai":
            client = OpenAIProvider(api_key=api_key, base_url=base_url or "https://api.openai.com/v1")
        elif provider_type == "openai_compatible":
            client = OpenAICompatibleProvider(api_key=api_key, base_url=base_url)
        elif provider_type == "anthropic":
            client = AnthropicProvider(api_key=api_key, base_url=base_url or "https://api.anthropic.com")
        else:
            raise ValidationError("Gemini 暂不支持在线拉取模型列表，请手动填写。")

        list_fn = getattr(client, "list_models", None)
        if list_fn is None:
            raise ValidationError("该提供商类型暂不支持在线拉取模型列表。")
        models = list_fn()
        if not models:
            raise ValidationError("API 未返回任何模型。")
        return {"models": models, "default_model": models[0], "source": "api"}
