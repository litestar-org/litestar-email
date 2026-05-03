"""Base protocols for HTTP transports.

This module defines the Protocol classes that all HTTP transports must implement.
Using Protocols enables structural subtyping, allowing any object with matching
methods to be used as a transport without inheriting from a base class.
"""

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Mapping

    from typing_extensions import Self

__all__ = (
    "HTTPResponse",
    "HTTPTransport",
)


@runtime_checkable
class HTTPResponse(Protocol):
    """Protocol for HTTP response objects.

    This protocol defines the minimal interface that transport-specific
    response objects must implement. Using a protocol enables structural
    subtyping, allowing any object with these attributes/methods to be used.

    Example:
        Accessing response data::

            response = await transport.post(url, json=payload)
            if response.status_code == 429:
                retry_after = response.get_header("Retry-After")
                raise RateLimitError(retry_after=retry_after)
            body = await response.text()
    """

    __slots__ = ()

    @property
    def status_code(self) -> int:
        """HTTP status code (e.g., 200, 404, 500)."""
        ...

    async def text(self) -> str:
        """Get response body as decoded text.

        Returns:
            The response body as a string.

        Note:
            This method may cache the result after first call for efficiency.
        """
        ...

    def get_header(self, name: str, default: str | None = None) -> str | None:
        """Get a response header by name.

        Args:
            name: Header name (case-insensitive).
            default: Value to return if header not found.

        Returns:
            Header value or default.
        """
        ...


@runtime_checkable
class HTTPTransport(Protocol):
    """Protocol for async HTTP transports.

    This protocol defines the interface for HTTP client adapters.
    Implementations must support async context manager protocol
    for proper resource management.

    The transport supports both JSON APIs (Resend, SendGrid) and
    form-data APIs (Mailgun) through the flexible post() method.

    Example:
        Using a transport with JSON API::

            transport = get_transport("httpx")
            await transport.open(
                headers={"Authorization": "Bearer token"},
                timeout=30.0,
            )
            try:
                response = await transport.post(url, json={"key": "value"})
            finally:
                await transport.close()

        Using a transport with form-data API::

            transport = get_transport("httpx")
            await transport.open(
                auth=("api", "key-xxx"),
                base_url="https://api.mailgun.net",
                timeout=30.0,
            )
            try:
                response = await transport.post(
                    "/v3/domain/messages",
                    data={"from": "sender@example.com", "to": "recipient@example.com"},
                    files=[("attachment", ("file.txt", b"content", "text/plain"))],
                )
            finally:
                await transport.close()
    """

    __slots__ = ()

    async def open(
        self,
        headers: "Mapping[str, str] | None" = None,
        timeout: float = 30.0,
        auth: tuple[str, str] | None = None,
        base_url: str | None = None,
    ) -> None:
        """Initialize the transport with configuration.

        Args:
            headers: Default headers to include in all requests.
            timeout: Request timeout in seconds.
            auth: HTTP Basic Auth credentials as (username, password).
                Used by Mailgun for API key authentication.
            base_url: Base URL to prepend to all request URLs.
                Used by Mailgun for regional endpoint selection.
        """
        ...

    async def close(self) -> None:
        """Close the transport and release resources."""
        ...

    async def post(
        self,
        url: str,
        *,
        json: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        files: list[tuple[str, tuple[str, bytes, str]]] | None = None,
        content: bytes | None = None,
        headers: "Mapping[str, str] | None" = None,
    ) -> HTTPResponse:
        """Make a POST request.

        Supports JSON, form-data, and pre-serialized bytes request bodies:

        - Use ``json`` for JSON APIs that don't require body-byte stability (Resend, SendGrid).
        - Use ``data`` and ``files`` for form-data APIs (Mailgun).
        - Use ``content`` for pre-serialized bytes that must hit the wire unchanged
          (Amazon SES with SigV4, where the request body must byte-for-byte match
          what was signed).

        Args:
            url: The URL to POST to. May be relative if base_url was set.
            json: Dictionary to serialize as JSON body. Mutually exclusive with data and content.
            data: Dictionary for form-data body. Used with files for multipart requests.
            files: List of file tuples for multipart upload.
                Each tuple is (field_name, (filename, content, content_type)).
            content: Raw bytes to use as the request body verbatim. The caller is
                responsible for setting an appropriate ``Content-Type`` header.
            headers: Optional headers to include in this specific request.
                These will be merged with or override the default transport headers.

        Returns:
            Response object conforming to HTTPResponse protocol.

        Raises:
            EmailConnectionError: If connection fails or times out.
        """
        ...

    async def __aenter__(self) -> "Self":
        """Enter async context manager."""
        ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Exit async context manager."""
        ...
