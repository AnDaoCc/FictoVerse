from unittest.mock import patch

from novel_world.modules.ai.providers.edge_tts_provider import EdgeTTSProvider


def test_strip_in_provider_synthesize_empty() -> None:
    provider = EdgeTTSProvider()
    assert provider.synthesize("   ") == b""


@patch("novel_world.modules.ai.providers.edge_tts_provider.asyncio.run")
def test_edge_synthesize_calls_async(mock_run) -> None:
    mock_run.return_value = b"audio"
    provider = EdgeTTSProvider(voice="zh-CN-XiaoxiaoNeural")
    out = provider.synthesize("hello", voice="zh-CN-YunxiNeural", rate=1.0)
    assert out == b"audio"
    mock_run.assert_called_once()


def test_list_voices_fallback_without_edge_tts() -> None:
    import novel_world.modules.ai.providers.edge_tts_provider as mod

    mod._VOICE_CACHE = None
    with patch("novel_world.modules.ai.providers.edge_tts_provider._run_async", side_effect=Exception("no edge-tts")):
        voices = EdgeTTSProvider().list_voices(locale_prefix="zh")
        assert any(v["id"].startswith("zh-CN") for v in voices)


def test_media_type() -> None:
    assert EdgeTTSProvider().media_type() == "audio/mpeg"
