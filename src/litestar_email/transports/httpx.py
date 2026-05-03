"""HTTP transport implementation using httpx.

This module provides the default HTTP transport for API-based email backends.
httpx is bundled with Litestar, so it should be available in most deployments.
"""

from typing import TYPE_CHECKING, Any, cast

from typing_extensions import Self

from litestar_email.exceptions import EmailConnectionError
from litestar_email.utils.module_loader import ensure_httpx

if TYPE_CHECKING:
    from collections.abc import Mapping

    import httpx

__all__ = (
    "HttpxResponse",
    "HttpxTransport",
)


class HttpxResponse:
    """Response wrapper for httpx responses.

    Wraps httpx.Response to conform to the HTTPResponse protocol,
    providing a consistent interface regardless of the underlying
    HTTP library.

    The text() method is async for protocol compatibility, though
    httpx responses are already fully read.
    """

    __slots__ = ("_response",)

    def __init__(self, response: "httpx.Response") -> None:
        """Initialize with an httpx response.

        Args:
            response: The httpx Response object to wrap.
        """
        self._response = response

    @property
    def status_code(self) -> int:
        """HTTP status code."""
        return self._response.status_code

    async def text(self) -> str:
        """Get response body as text.

        Returns:
            The response body as a decoded string.

        Note:
            This is async for protocol compatibility. httpx responses
            are already fully read, so this is effectively synchronous.
        """
        return self._response.text

    def get_header(self, name: str, default: str | None = None) -> str | None:
        """Get a response header by name.

        Args:
            name: Header name (case-insensitive).
            default: Value to return if header not found.

        Returns:
            Header value or default.
        """
        return cast("str | None", self._response.headers.get(name, default))


class HttpxTransport:
    """HTTP transport implementation using httpx.

    This is the default transport for API-based email backends.
    It provides async HTTP operations with automatic connection pooling.

    Connection pooling is handled automatically by httpx.AsyncClient:
    - Default: 100 max connections, 10 per host
    - Keep-alive enabled by default
    - Connections are reused across multiple requests within a session

    Supports both JSON APIs (Resend, SendGrid) and form-data APIs (Mailgun)
    through the flexible post() method.

    Example:
        Basic usage with JSON API::

            transport = HttpxTransport()
            await transport.open(
                headers={"Authorization": "Bearer xxx"},
                timeout=30.0,
            )
            response = await transport.post(
                "https://api.resend.com/emails",
                json={"to": "user@example.com", "subject": "Hello"},
            )
            await transport.close()

        Usage with form-data API (Mailgun)::

            transport = HttpxTransport()
            await transport.open(
                auth=("api", "key-xxx"),
                base_url="https://api.mailgun.net",
                timeout=30.0,
            )
            response = await transport.post(
                "/v3/domain/messages",
                data={"from": "sender@example.com", "to": "recipient@example.com"},
                files=[("attachment", ("file.txt", b"content", "text/plain"))],
            )
            await transport.close()
    """

    __slots__ = ("_client",)

    def __init__(self) -> None:
        """Initialize httpx transport.

        Note:
            May raise ``MissingDependencyError`` if httpx is not installed.
        """
        ensure_httpx()
        self._client: "httpx.AsyncClient | None" = None

    async def open(
        self,
        headers: "Mapping[str, str] | None" = None,
        timeout: float = 30.0,
        auth: tuple[str, str] | None = None,
        base_url: str | None = None,
    ) -> None:
        """Initialize the HTTP client.

        Args:
            headers: Default headers for all requests.
            timeout: Request timeout in seconds.
            auth: HTTP Basic Auth credentials as (username, password).
            base_url: Base URL to prepend to all request URLs.
        """
        if self._client is not None:
            return

        import httpx

        # Configure connection pool limits for email API workloads
        # - max_connections: Total connections across all hosts
        # - max_keepalive_connections: Connections to keep alive in pool
        # - keepalive_expiry: How long to keep idle connections (seconds)
        limits = httpx.Limits(
            max_connections=100,
            max_keepalive_connections=20,
            keepalive_expiry=30.0,
        )

        client_kwargs: dict[str, Any] = {
            "timeout": timeout,
            "limits": limits,
        }

        if headers:
            client_kwargs["headers"] = dict(headers)

        if auth:
            client_kwargs["auth"] = auth

        if base_url:
            client_kwargs["base_url"] = base_url

        self._client = httpx.AsyncClient(**client_kwargs)

    async def close(self) -> None:
        """Close the HTTP client and release resources."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def post(
        self,
        url: str,
        *,
        json: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        files: list[tuple[str, tuple[str, bytes, str]]] | None = None,
        headers: "Mapping[str, str] | None" = None,
    ) -> HttpxResponse:
        """Make a POST request.

        Args:
            url: The URL to POST to.
            json: Dictionary to serialize as JSON body.
            data: Dictionary for form-data body.
            files: List of file tuples for multipart upload.
            headers: Optional headers to include in this specific request.

        Returns:
            Response wrapped in HttpxResponse.

        Raises:
            RuntimeError: If transport not initialized.
            EmailConnectionError: If connection fails or times out.
        """
        if self._client is None:
            msg = "Transport not initialized. Call open() first."
            raise RuntimeError(msg)

        import httpx

        try:
            response = await self._client.post(url, json=json, data=data, files=files, headers=dict(headers) if headers else None)
            return HttpxResponse(response)
        except httpx.ConnectError as exc:
            msg = f"Connection failed: {exc}"
            raise EmailConnectionError(msg) from exc
        except httpx.TimeoutException as exc:
            msg = f"Request timed out: {exc}"
            raise EmailConnectionError(msg) from exc

    async def __aenter__(self) -> Self:
        """Enter async context manager.

        Returns:
            Self for use in async with statements.
        """
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Exit async context manager."""
        await self.close()
