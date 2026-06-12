from __future__ import annotations

from unittest.mock import MagicMock, patch

from novel_world.modules.ai.providers.openai_provider import OpenAIProvider


def test_openai_provider_list_models() -> None:
    provider = OpenAIProvider(api_key="sk-test", base_url="https://api.example.com/v1")
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "data": [{"id": "deepseek-v4-pro"}, {"id": "deepseek-v4-flash"}],
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("novel_world.modules.ai.providers.openai_provider.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        models = provider.list_models()

    assert models == ["deepseek-v4-flash", "deepseek-v4-pro"]
