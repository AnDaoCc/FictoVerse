from __future__ import annotations

from dataclasses import dataclass

from novel_world.modules.ai.domain.entities import ProviderType


@dataclass(frozen=True)
class VendorPreset:
    slug: str
    name: str
    vendor: str
    provider_type: ProviderType
    base_url: str
    default_model: str
    models: tuple[str, ...]
    api_key_hint: str
    description: str


VENDOR_CATALOG: tuple[VendorPreset, ...] = (
    VendorPreset(
        slug="openai",
        name="OpenAI GPT",
        vendor="OpenAI",
        provider_type="openai",
        base_url="https://api.openai.com/v1",
        default_model="gpt-4o-mini",
        models=("gpt-4o", "gpt-4o-mini", "gpt-4.1-mini", "o3-mini"),
        api_key_hint="sk-...",
        description="官方 OpenAI API",
    ),
    VendorPreset(
        slug="anthropic",
        name="Anthropic Claude",
        vendor="Anthropic",
        provider_type="anthropic",
        base_url="https://api.anthropic.com",
        default_model="claude-3-5-sonnet-latest",
        models=("claude-3-5-sonnet-latest", "claude-3-5-haiku-latest", "claude-3-opus-latest"),
        api_key_hint="sk-ant-...",
        description="官方 Claude API",
    ),
    VendorPreset(
        slug="gemini",
        name="Google Gemini",
        vendor="Google",
        provider_type="gemini",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        default_model="gemini-2.0-flash",
        models=("gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"),
        api_key_hint="AIza...",
        description="官方 Gemini API",
    ),
    VendorPreset(
        slug="deepseek",
        name="DeepSeek",
        vendor="DeepSeek",
        provider_type="openai_compatible",
        base_url="https://api.deepseek.com/v1",
        default_model="deepseek-v4-flash",
        models=(
            "deepseek-v4-pro",
            "deepseek-v4-flash",
            "deepseek-chat",
            "deepseek-reasoner",
        ),
        api_key_hint="sk-...",
        description="DeepSeek 官方 OpenAI 兼容接口",
    ),
    VendorPreset(
        slug="moonshot",
        name="Moonshot Kimi",
        vendor="Moonshot",
        provider_type="openai_compatible",
        base_url="https://api.moonshot.cn/v1",
        default_model="moonshot-v1-8k",
        models=("moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"),
        api_key_hint="sk-...",
        description="月之暗面 Kimi",
    ),
    VendorPreset(
        slug="zhipu",
        name="智谱 GLM",
        vendor="Zhipu",
        provider_type="openai_compatible",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        default_model="glm-4-flash",
        models=("glm-4-flash", "glm-4-plus", "glm-4-air"),
        api_key_hint="...",
        description="智谱 AI 官方接口",
    ),
    VendorPreset(
        slug="qwen",
        name="通义千问",
        vendor="Alibaba",
        provider_type="openai_compatible",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        default_model="qwen-plus",
        models=("qwen-plus", "qwen-turbo", "qwen-max"),
        api_key_hint="sk-...",
        description="阿里云 DashScope 兼容模式",
    ),
    VendorPreset(
        slug="openrouter",
        name="OpenRouter",
        vendor="OpenRouter",
        provider_type="openai_compatible",
        base_url="https://openrouter.ai/api/v1",
        default_model="openai/gpt-4o-mini",
        models=("openai/gpt-4o-mini", "anthropic/claude-3.5-sonnet", "google/gemini-2.0-flash-exp:free"),
        api_key_hint="sk-or-...",
        description="聚合多家模型的中转平台",
    ),
    VendorPreset(
        slug="ollama",
        name="Ollama 本地",
        vendor="Ollama",
        provider_type="openai_compatible",
        base_url="http://127.0.0.1:11434/v1",
        default_model="llama3.2",
        models=("llama3.2", "qwen2.5", "mistral", "deepseek-r1"),
        api_key_hint="可留空",
        description="本地 Ollama OpenAI 兼容接口",
    ),
    VendorPreset(
        slug="custom_relay",
        name="第三方中转站",
        vendor="Relay",
        provider_type="openai_compatible",
        base_url="",
        default_model="gpt-4o-mini",
        models=("gpt-4o-mini", "claude-3-5-sonnet", "gemini-2.0-flash"),
        api_key_hint="从中转站获取",
        description="任意 OpenAI 兼容 Base URL",
    ),
)


def get_preset(slug: str) -> VendorPreset | None:
    for preset in VENDOR_CATALOG:
        if preset.slug == slug:
            return preset
    return None


def catalog_as_dicts() -> list[dict]:
    return [
        {
            "slug": p.slug,
            "name": p.name,
            "vendor": p.vendor,
            "provider_type": p.provider_type,
            "base_url": p.base_url,
            "default_model": p.default_model,
            "models": list(p.models),
            "api_key_hint": p.api_key_hint,
            "description": p.description,
        }
        for p in VENDOR_CATALOG
    ]
