"""Transport factory.

Public API: :func:`get_transport`. Re-exported from
:mod:`litestar_email.transports`.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from litestar_email.transports.base import HTTPTransport

__all__ = ("get_transport",)


def get_transport(transport: 'str | type["HTTPTransport"]' = "httpx") -> "HTTPTransport":
    """Get an HTTP transport instance by name or from a custom class.

    This factory function provides a convenient way to obtain transport instances.
    It supports built-in transports by name and custom transport classes.

    Args:
        transport: Either a string name ("httpx" or "aiohttp") or a custom
            transport class that implements the HTTPTransport protocol.
            Defaults to "httpx".

    Returns:
        An instance of the requested transport.

    Raises:
        ValueError: If an unknown transport name is provided.

    Example:
        Get the default httpx transport::

            transport = get_transport()

        Get the aiohttp transport::

            transport = get_transport("aiohttp")

        Use a custom transport class::

            transport = get_transport(MyCustomTransport)
    """
    if isinstance(transport, str):
        if transport == "httpx":
            from litestar_email.transports.httpx import HttpxTransport

            return HttpxTransport()

        if transport == "aiohttp":
            from litestar_email.transports.aiohttp import AiohttpTransport

            return AiohttpTransport()

        msg = f"Unknown transport: {transport!r}. Available transports: 'httpx', 'aiohttp'"
        raise ValueError(msg)

    return transport()
