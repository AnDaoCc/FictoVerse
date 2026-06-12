from novel_world.modules.ai.providers.tts_registry import (
    build_tts_provider,
    normalize_tts_backend,
)


def test_normalize_tts_backend_openai_alias() -> None:
    assert normalize_tts_backend("openai") == "openai_compatible"
    assert normalize_tts_backend("edge") == "edge"


def test_build_tts_provider_openai_requires_key() -> None:
    assert build_tts_provider({"tts_backend": "openai", "tts_openai_api_key": ""}) is None
    assert build_tts_provider({"tts_backend": "openai_compatible", "tts_openai_api_key": "sk-test"}) is not None


def test_build_tts_provider_openai_voices_without_key() -> None:
    provider = build_tts_provider(
        {"tts_backend": "openai_compatible", "tts_openai_api_key": ""},
        require_credentials=False,
    )
    assert provider is not None
    voices = provider.list_voices()
    assert len(voices) >= 6


def test_build_tts_provider_custom_http_requires_url() -> None:
    assert build_tts_provider({"tts_backend": "custom_http", "tts_custom": {}}) is None
    provider = build_tts_provider(
        {"tts_backend": "custom_http", "tts_custom": {"url": "http://127.0.0.1:7851/tts"}},
    )
    assert provider is not None


def test_build_tts_provider_edge() -> None:
    provider = build_tts_provider({"tts_backend": "edge"})
    assert provider is not None
