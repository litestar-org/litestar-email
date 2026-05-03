"""Tests for per-request headers in HTTP transports."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.anyio


async def test_httpx_transport_post_with_custom_headers() -> None:
    """Test HttpxTransport.post passes per-request headers."""
    from litestar_email.transports.httpx import HttpxTransport

    transport = HttpxTransport()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "OK"
    mock_response.headers = {}

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        await transport.open()
        custom_headers = {"X-Custom-Header": "custom-value"}

        # This should fail if we haven't updated the signature yet,
        # or if we have updated it but aren't passing it to the client.
        await transport.post("https://api.example.com", json={"key": "value"}, headers=custom_headers)

        # Verify headers were passed to post call
        _args, kwargs = mock_client.post.call_args
        assert kwargs.get("headers") == custom_headers


async def test_aiohttp_transport_post_with_custom_headers() -> None:
    """Test AiohttpTransport.post passes per-request headers."""
    from litestar_email.transports.aiohttp import AiohttpTransport

    transport = AiohttpTransport()
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.headers = {}
    mock_response.text = AsyncMock(return_value="OK")

    with patch("aiohttp.ClientSession") as mock_session_class:
        mock_session = MagicMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_session.close = AsyncMock()
        mock_session_class.return_value = mock_session

        await transport.open()
        custom_headers = {"X-Custom-Header": "custom-value"}

        await transport.post("https://api.example.com", json={"key": "value"}, headers=custom_headers)

        # Verify headers were passed to post call
        _args, kwargs = mock_session.post.call_args
        assert kwargs.get("headers") == custom_headers
