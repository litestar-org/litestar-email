"""HTTP transport layer for API-based email backends.

This package provides pluggable HTTP transport implementations for email backends
that communicate via HTTP APIs (Resend, SendGrid, Mailgun, SES).

The default transport is httpx, which is bundled with Litestar. Users can opt
into aiohttp for applications that already use it, or provide custom transport
implementations.

Example:
    Using the default httpx transport::

        from litestar_email.transports import get_transport

        transport = get_transport()  # Returns HttpxTransport
        await transport.open(headers={"Authorization": "Bearer xxx"})
        response = await transport.post(url, json=payload)
        await transport.close()

    Using aiohttp transport::

        transport = get_transport("aiohttp")
"""

from typing import TYPE_CHECKING

from litestar_email.transports.base import HTTPResponse, HTTPTransport
from litestar_email.transports.factory import get_transport

if TYPE_CHECKING:
    from litestar_email.transports.aiohttp import AiohttpResponse, AiohttpTransport
    from litestar_email.transports.httpx import HttpxResponse, HttpxTransport

__all__ = (
    "AiohttpResponse",
    "AiohttpTransport",
    "HTTPResponse",
    "HTTPTransport",
    "HttpxResponse",
    "HttpxTransport",
    "get_transport",
)


def __getattr__(name: str) -> object:
    """Lazy import for transport implementations.

    Loads transport classes only when accessed so optional HTTP-client dependencies
    are not imported at package import time.

    Args:
        name: The attribute name to look up.

    Returns:
        The requested transport class.

    Raises:
        AttributeError: If the attribute is not a known transport class.
    """
    if name == "HttpxTransport":
        from litestar_email.transports.httpx import HttpxTransport

        return HttpxTransport

    if name == "HttpxResponse":
        from litestar_email.transports.httpx import HttpxResponse

        return HttpxResponse

    if name == "AiohttpTransport":
        from litestar_email.transports.aiohttp import AiohttpTransport

        return AiohttpTransport

    if name == "AiohttpResponse":
        from litestar_email.transports.aiohttp import AiohttpResponse

        return AiohttpResponse

    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
