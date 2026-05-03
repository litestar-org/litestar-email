"""HTTP transport implementation using aiohttp.

This module provides an alternative HTTP transport for API-based email backends.
aiohttp is useful for applications that already depend on it and want to avoid
adding httpx as an additional dependency.

Note:
    aiohttp must be installed separately: ``pip install litestar-email[aiohttp]``
"""

from typing import TYPE_CHECKING, Any

from typing_extensions import Self

from litestar_email.exceptions import EmailConnectionError
from litestar_email.utils.module_loader import ensure_aiohttp

if TYPE_CHECKING:
    from collections.abc import Mapping

    import aiohttp

__all__ = (
    "AiohttpResponse",
    "AiohttpTransport",
)


class AiohttpResponse:
    """Response wrapper for aiohttp responses with lazy body reading.

    Wraps aiohttp.ClientResponse to conform to the HTTPResponse protocol.
    The response body is read lazily on first access to text() and cached
    for subsequent calls.

    This lazy approach is important because aiohttp responses stream their
    body by default, and the body can only be read once. Caching ensures
    consistent behavior across multiple text() calls.

    Note:
        The response object is kept alive until the transport is closed
        or the response body is read. This is necessary because aiohttp
        responses are streaming and cannot be read after the connection
        context is closed.
    """

    __slots__ = ("_headers", "_response", "_status_code", "_text_cache")

    def __init__(self, response: "aiohttp.ClientResponse") -> None:
        """Initialize with an aiohttp response.

        Args:
            response: The aiohttp ClientResponse object to wrap.
        """
        self._response = response
        self._status_code = response.status
        self._headers = response.headers
        self._text_cache: str | None = None

    @property
    def status_code(self) -> int:
        """HTTP status code."""
        return self._status_code

    async def text(self) -> str:
        """Get response body as text.

        The body is read on first call and cached for subsequent calls.
        This is necessary because aiohttp response bodies can only be
        read once.

        Returns:
            The response body as a decoded string.
        """
        if self._text_cache is None:
            self._text_cache = await self._response.text()
        return self._text_cache

    def get_header(self, name: str, default: str | None = None) -> str | None:
        """Get a response header by name.

        Args:
            name: Header name (case-insensitive).
            default: Value to return if header not found.

        Returns:
            Header value or default.
        """
        return self._headers.get(name, default)


class AiohttpTransport:
    """HTTP transport implementation using aiohttp.

    This is an alternative transport for API-based email backends.
    It provides async HTTP operations with automatic connection pooling
    via aiohttp's TCPConnector.

    Connection pooling is handled by TCPConnector:
    - Default: 100 max connections, 10 per host
    - Keep-alive enabled with 30s timeout
    - TCP_NODELAY enabled for low latency

    Supports both JSON APIs (Resend, SendGrid) and form-data APIs (Mailgun)
    through the flexible post() method.

    Example:
        Basic usage with JSON API::

            transport = AiohttpTransport()
            await transport.open(
                headers={"Authorization": "Bearer xxx"},
                timeout=30.0,
            )
            response = await transport.post(
                "https://api.resend.com/emails",
                json={"to": "user@example.com", "subject": "Hello"},
            )
            body = await response.text()  # Lazy read
            await transport.close()

        Usage with form-data API (Mailgun)::

            transport = AiohttpTransport()
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

    __slots__ = ("_auth", "_base_url", "_connector", "_session")

    def __init__(self) -> None:
        """Initialize aiohttp transport.

        Note:
            May raise ``MissingDependencyError`` if aiohttp is not installed.
        """
        ensure_aiohttp()
        self._session: "aiohttp.ClientSession | None" = None
        self._connector: "aiohttp.TCPConnector | None" = None
        self._auth: "aiohttp.BasicAuth | None" = None
        self._base_url: str | None = None

    async def open(
        self,
        headers: "Mapping[str, str] | None" = None,
        timeout: float = 30.0,
        auth: tuple[str, str] | None = None,
        base_url: str | None = None,
    ) -> None:
        """Initialize the HTTP client session.

        Args:
            headers: Default headers for all requests.
            timeout: Request timeout in seconds.
            auth: HTTP Basic Auth credentials as (username, password).
            base_url: Base URL to prepend to all request URLs.
        """
        if self._session is not None:
            return

        import aiohttp

        # Configure connection pool for email API workloads
        # - limit: Total connections across all hosts
        # - limit_per_host: Max connections per host (email APIs are single-host)
        # - keepalive_timeout: How long to keep idle connections
        self._connector = aiohttp.TCPConnector(
            limit=100,
            limit_per_host=10,
            keepalive_timeout=30.0,
        )

        session_kwargs: dict[str, Any] = {
            "timeout": aiohttp.ClientTimeout(total=timeout),
            "connector": self._connector,
        }

        if headers:
            session_kwargs["headers"] = dict(headers)

        if auth:
            self._auth = aiohttp.BasicAuth(login=auth[0], password=auth[1])

        if base_url:
            self._base_url = base_url.rstrip("/")

        self._session = aiohttp.ClientSession(**session_kwargs)

    async def close(self) -> None:
        """Close the HTTP client session and release resources."""
        if self._session is not None:
            await self._session.close()
            self._session = None
        if self._connector is not None:
            await self._connector.close()
            self._connector = None
        self._auth = None
        self._base_url = None

    def _build_form_data(
        self,
        data: dict[str, Any] | None,
        files: list[tuple[str, tuple[str, bytes, str]]] | None,
    ) -> "aiohttp.FormData":
        """Build aiohttp FormData from data dict and files.

        Args:
            data: Dictionary of form field values.
            files: List of file tuples (field_name, (filename, content, content_type)).

        Returns:
            Populated aiohttp FormData object.
        """
        import aiohttp

        form_data = aiohttp.FormData()

        if data:
            for key, value in data.items():
                # Handle list values (multiple recipients, etc.)
                if isinstance(value, list):
                    for item in value:
                        form_data.add_field(key, str(item))
                else:
                    form_data.add_field(key, str(value))

        if files:
            for field_name, (filename, content, content_type) in files:
                form_data.add_field(
                    field_name,
                    content,
                    filename=filename,
                    content_type=content_type,
                )

        return form_data

    async def post(
        self,
        url: str,
        *,
        json: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        files: list[tuple[str, tuple[str, bytes, str]]] | None = None,
        content: bytes | None = None,
        headers: "Mapping[str, str] | None" = None,
    ) -> AiohttpResponse:
        """Make a POST request.

        Args:
            url: The URL to POST to. May be relative if base_url was set.
            json: Dictionary to serialize as JSON body.
            data: Dictionary for form-data body.
            files: List of file tuples for multipart upload.
            content: Raw bytes to use as the request body verbatim. Mutually exclusive
                with ``json``/``data``/``files``. Required for byte-stable signed requests.
            headers: Optional headers to include in this specific request.

        Returns:
            Response wrapped in AiohttpResponse with lazy body reading.

        Raises:
            RuntimeError: If transport not initialized.
            EmailConnectionError: If connection fails or times out.
        """
        if self._session is None:
            msg = "Transport not initialized. Call open() first."
            raise RuntimeError(msg)

        import aiohttp

        # Build full URL if base_url is set
        full_url = url
        if self._base_url and not url.startswith(("http://", "https://")):
            full_url = f"{self._base_url}/{url.lstrip('/')}"

        try:
            # Build request kwargs
            request_kwargs: dict[str, Any] = {}

            if self._auth:
                request_kwargs["auth"] = self._auth

            if headers:
                request_kwargs["headers"] = dict(headers)

            if content is not None:
                request_kwargs["data"] = content
            elif json is not None:
                request_kwargs["json"] = json
            elif data is not None or files is not None:
                request_kwargs["data"] = self._build_form_data(data, files)

            # Don't use `async with` - we need the response to stay alive
            # for lazy body reading
            response = await self._session.post(full_url, **request_kwargs)
            return AiohttpResponse(response)

        except aiohttp.ClientConnectorError as exc:
            msg = f"Connection failed: {exc}"
            raise EmailConnectionError(msg) from exc
        except TimeoutError as exc:
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
