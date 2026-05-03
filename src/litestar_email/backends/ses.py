"""Amazon SES email backend using the SES API v2."""

import json
from typing import TYPE_CHECKING, Any

from litestar_email.backends.base import BaseEmailBackend
from litestar_email.exceptions import (
    EmailAuthenticationError,
    EmailDeliveryError,
    EmailRateLimitError,
)
from litestar_email.utils.module_loader import ensure_botocore, ensure_httpx

if TYPE_CHECKING:
    from litestar_email.config import SESConfig
    from litestar_email.message import EmailMessage
    from litestar_email.transports.base import HTTPTransport

__all__ = ("SESBackend",)


class SESBackend(BaseEmailBackend):
    """Amazon SES email backend using the API v2.

    This backend sends emails via Amazon SES API v2, which provides better
    performance and more features than the SMTP interface.

    The backend uses ``botocore`` for AWS Signature Version 4 (SigV4)
    authentication.

    Example:
        Basic usage::

            config = EmailConfig(
                backend="ses",
                from_email="noreply@example.com",
                backend_config=SESConfig(region="us-east-1"),
            )
            backend = get_backend("ses", config=config)
            async with backend:
                await backend.send_messages([message])
    """

    __slots__ = ("_config", "_transport")

    def __init__(
        self,
        config: "SESConfig | None" = None,
        fail_silently: bool = False,
        default_from_email: str | None = None,
        default_from_name: str | None = None,
    ) -> None:
        """Initialize SES backend.

        Args:
            config: SES configuration settings. If None, defaults are used.
            fail_silently: If True, suppress exceptions during send.
            default_from_email: Default sender email when message.from_email is missing.
            default_from_name: Default sender name when message.from_email has no name.

        Note:
            May raise ``MissingDependencyError`` if botocore or the configured
            HTTP transport is not installed.
        """
        ensure_botocore()

        super().__init__(
            fail_silently=fail_silently,
            default_from_email=default_from_email,
            default_from_name=default_from_name,
        )

        # Use provided config or create default
        if config is None:
            from litestar_email.config import SESConfig

            config = SESConfig()

        # Check httpx availability if using default transport
        if config.http_transport == "httpx":
            ensure_httpx()

        self._config = config
        self._transport: "HTTPTransport | None" = None

    async def open(self) -> bool:
        """Open an HTTP transport for sending emails.

        Returns:
            True if a new transport was created, False if reusing existing.
        """
        if self._transport is not None:
            return False

        from litestar_email.transports import get_transport

        self._transport = get_transport(self._config.http_transport)
        await self._transport.open(
            timeout=float(self._config.timeout),
        )
        return True

    async def close(self) -> None:
        """Close the HTTP transport."""
        if self._transport is not None:
            try:
                await self._transport.close()
            except Exception:
                if not self.fail_silently:
                    raise
            finally:
                self._transport = None

    async def send_messages(self, messages: list["EmailMessage"]) -> int:
        """Send messages via Amazon SES API v2.

        Args:
            messages: List of EmailMessage instances to send.

        Returns:
            Number of messages successfully sent.

        Raises:
            EmailDeliveryError: If sending fails and fail_silently is False.
            EmailRateLimitError: If rate limited by the API.
            EmailAuthenticationError: If AWS credentials are rejected.
        """
        if not messages:
            return 0

        new_connection = await self.open()

        try:
            num_sent = 0
            for message in messages:
                try:
                    await self._send_message(message)
                    num_sent += 1
                except (EmailRateLimitError, EmailAuthenticationError):
                    # Always propagate — fail_silently is for transient delivery
                    # errors, not "stop sending" signals.
                    raise
                except EmailDeliveryError:
                    # Preserve the typed message from _send_message (e.g.
                    # attachments, empty-body, 4xx detail) instead of re-wrapping.
                    if not self.fail_silently:
                        raise
                except Exception as exc:
                    if not self.fail_silently:
                        msg = f"Failed to send email to {message.to} via Amazon SES"
                        raise EmailDeliveryError(msg) from exc
            return num_sent
        finally:
            if new_connection:
                await self.close()

    async def _send_message(self, message: "EmailMessage") -> None:
        """Send a single message via Amazon SES API v2.

        The request body is serialized once and the resulting bytes are both
        signed (via SigV4) and put on the wire verbatim. This is required
        because SigV4 includes ``x-amz-content-sha256`` of the body, so any
        re-serialization (e.g., httpx switching separators) would invalidate
        the signature.

        Args:
            message: The email message to send.

        Raises:
            RuntimeError: If transport is not initialized.
            EmailRateLimitError: If rate limited by the API.
            EmailAuthenticationError: If AWS credentials are rejected.
            EmailDeliveryError: If the API returns an error or the message
                is unsupported by the SES Simple content type.
        """
        if self._transport is None:
            msg = "SES transport not initialized"
            raise RuntimeError(msg)

        # SES v2 ``Simple`` content does not support attachments — those require
        # ``Raw`` content (a fully-formed MIME message). Fail loudly rather than
        # silently dropping data.
        if message.attachments:
            msg = (
                "Amazon SES backend does not support attachments via the Simple "
                "content type. Use the SMTP backend or send a Raw MIME message."
            )
            raise EmailDeliveryError(msg)

        # Build the request payload (SES v2 schema).
        _, _, from_formatted = self._resolve_from(message)
        body_section: dict[str, Any] = {}
        if message.body:
            body_section["Text"] = {"Data": message.body}
        for content, mimetype in message.alternatives:
            if mimetype == "text/html":
                body_section["Html"] = {"Data": content}
                break

        if not body_section:
            msg = "Amazon SES requires either a text body or an HTML alternative"
            raise EmailDeliveryError(msg)

        payload: dict[str, Any] = {
            "FromEmailAddress": from_formatted,
            "Destination": {"ToAddresses": message.to},
            "Content": {
                "Simple": {
                    "Subject": {"Data": message.subject},
                    "Body": body_section,
                }
            },
        }
        if message.cc:
            payload["Destination"]["CcAddresses"] = message.cc
        if message.bcc:
            payload["Destination"]["BccAddresses"] = message.bcc
        if message.reply_to:
            payload["ReplyToAddresses"] = message.reply_to

        url = f"https://email.{self._config.region}.amazonaws.com/v2/email/outbound-emails"
        body = json.dumps(payload).encode("utf-8")

        # Sign the *exact* bytes that will be transmitted, then send them as
        # raw content so transport-layer JSON re-serialization cannot diverge.
        headers = dict(self._sign_request(url, body))
        headers.setdefault("Content-Type", "application/json")

        response = await self._transport.post(
            url,
            content=body,
            headers=headers,
        )

        if response.status_code == 429:
            retry_after = response.get_header("Retry-After")
            retry_seconds = int(retry_after) if retry_after else None
            msg = "Amazon SES API rate limit exceeded"
            raise EmailRateLimitError(msg, retry_after=retry_seconds)

        if response.status_code == 403:
            error_detail = await response.text()
            msg = f"Amazon SES authentication failed: {error_detail}"
            raise EmailAuthenticationError(msg)

        if response.status_code >= 400:
            error_detail = await response.text()
            msg = f"Amazon SES API error: {response.status_code} - {error_detail}"
            raise EmailDeliveryError(msg)

    def _sign_request(self, url: str, body: bytes) -> dict[str, str]:
        """Sign the request using AWS Signature Version 4.

        Args:
            url: The full request URL.
            body: The request body as bytes.

        Returns:
            Dictionary of SigV4 headers.
        """
        from botocore.auth import SigV4Auth  # type: ignore[import-untyped]
        from botocore.awsrequest import AWSRequest  # type: ignore[import-untyped]
        from botocore.credentials import Credentials  # type: ignore[import-untyped]
        from botocore.session import get_session  # type: ignore[import-untyped]

        if self._config.aws_access_key_id and self._config.aws_secret_access_key:
            credentials = Credentials(
                access_key=self._config.aws_access_key_id,
                secret_key=self._config.aws_secret_access_key,
                token=self._config.aws_session_token,
            )
        else:
            session = get_session()
            credentials = session.get_credentials()

        request = AWSRequest(method="POST", url=url, data=body)
        SigV4Auth(credentials, "ses", self._config.region).add_auth(request)
        return dict(request.headers)
