"""Async SMTP email backend using aiosmtplib."""

from email.message import EmailMessage as StdEmailMessage
from typing import TYPE_CHECKING

from litestar_email.backends.base import BaseEmailBackend
from litestar_email.exceptions import (
    EmailAuthenticationError,
    EmailConnectionError,
    EmailDeliveryError,
)
from litestar_email.utils.module_loader import ensure_aiosmtplib

if TYPE_CHECKING:
    import aiosmtplib

    from litestar_email.config import SMTPConfig
    from litestar_email.message import EmailMessage

__all__ = ("SMTPBackend",)


class SMTPBackend(BaseEmailBackend):
    """Async SMTP email backend using aiosmtplib.

    This backend provides true async email sending without blocking the
    event loop. It supports connection pooling through the context manager
    protocol, TLS/SSL, and authentication.

    The backend requires the ``aiosmtplib`` package to be installed.
    Install it with::

        pip install litestar-email[smtp]

    Example:
        Basic usage with Mailpit (local development)::

            config = EmailConfig(
                backend="smtp",
                from_email="noreply@example.com",
                backend_config=SMTPConfig(host="localhost", port=1025),
            )
            backend = get_backend("smtp", config=config)
            async with backend:
                await backend.send_messages([message])

        Production usage with STARTTLS::

            config = EmailConfig(
                backend="smtp",
                from_email="noreply@example.com",
                backend_config=SMTPConfig(
                    host="smtp.example.com",
                    port=587,
                    username="user@example.com",
                    password="secret",
                    use_tls=True,
                ),
            )
    """

    __slots__ = ("_config", "_connection")

    def __init__(
        self,
        config: "SMTPConfig | None" = None,
        fail_silently: bool = False,
        default_from_email: str | None = None,
        default_from_name: str | None = None,
    ) -> None:
        """Initialize SMTP backend.

        Args:
            config: SMTP configuration settings. If None, defaults are used.
            fail_silently: If True, suppress exceptions during send.
            default_from_email: Default sender email when message.from_email is missing.
            default_from_name: Default sender name when message.from_email has no name.

        Note:
            May raise ``MissingDependencyError`` if aiosmtplib is not installed.
        """
        ensure_aiosmtplib()

        super().__init__(
            fail_silently=fail_silently,
            default_from_email=default_from_email,
            default_from_name=default_from_name,
        )

        # Use provided config or create default
        if config is None:
            from litestar_email.config import SMTPConfig

            config = SMTPConfig()

        self._config = config
        self._connection: "aiosmtplib.SMTP | None" = None

    async def open(self) -> bool:
        """Open a connection to the SMTP server.

        Returns:
            True if a new connection was opened, False if reusing existing.

        Raises:
            EmailConnectionError: If connection to the server fails.
            EmailAuthenticationError: If authentication fails.
        """
        if self._connection is not None:
            return False

        import aiosmtplib

        self._connection = aiosmtplib.SMTP(
            hostname=self._config.host,
            port=self._config.port,
            timeout=self._config.timeout,
            use_tls=self._config.use_ssl,  # use_tls in aiosmtplib means implicit SSL
            start_tls=False,  # Disable auto-STARTTLS
        )

        try:
            await self._connection.connect()

            # STARTTLS upgrade (separate from implicit SSL)
            if self._config.use_tls and not self._config.use_ssl:
                await self._connection.starttls()

            # Authenticate if credentials provided
            if self._config.username and self._config.password:
                try:
                    await self._connection.login(
                        self._config.username,
                        self._config.password,
                    )
                except aiosmtplib.SMTPAuthenticationError as exc:
                    self._connection = None
                    msg = f"SMTP authentication failed for {self._config.username}"
                    raise EmailAuthenticationError(msg) from exc

        except aiosmtplib.SMTPConnectError as exc:
            self._connection = None
            msg = f"Failed to connect to SMTP server {self._config.host}:{self._config.port}"
            if not self.fail_silently:
                raise EmailConnectionError(msg) from exc
            return False
        except EmailAuthenticationError:
            if not self.fail_silently:
                raise
            return False
        except Exception as exc:
            self._connection = None
            msg = f"SMTP connection error: {exc}"
            if not self.fail_silently:
                raise EmailConnectionError(msg) from exc
            return False

        return True

    async def close(self) -> None:
        """Close the connection to the SMTP server."""
        if self._connection is not None:
            try:
                await self._connection.quit()
            except Exception:
                if not self.fail_silently:
                    raise
            finally:
                self._connection = None

    async def send_messages(self, messages: list["EmailMessage"]) -> int:
        """Send messages via SMTP.

        If not already connected, opens a connection for the duration
        of the send operation.

        Args:
            messages: List of EmailMessage instances to send.

        Returns:
            Number of messages successfully sent.

        Raises:
            EmailDeliveryError: If sending fails and fail_silently is False.
        """
        if not messages:
            return 0

        # Use context manager pattern if not already connected
        new_connection = await self.open()

        try:
            num_sent = 0
            for message in messages:
                try:
                    await self._send_message(message)
                    num_sent += 1
                except Exception as exc:
                    if not self.fail_silently:
                        msg = f"Failed to send email to {message.to}"
                        raise EmailDeliveryError(msg) from exc
            return num_sent

        finally:
            if new_connection:
                await self.close()

    async def _send_message(self, message: "EmailMessage") -> None:
        """Send a single message.

        Args:
            message: The email message to send.

        Raises:
            RuntimeError: If connection is not established.
        """
        if self._connection is None:
            msg = "SMTP connection not established"
            raise RuntimeError(msg)

        email_msg = self._build_message(message)
        await self._connection.send_message(email_msg)

    def _build_message(self, message: "EmailMessage") -> StdEmailMessage:
        """Convert EmailMessage to stdlib EmailMessage.

        Args:
            message: Our EmailMessage instance.

        Returns:
            Standard library EmailMessage instance.
        """
        msg = StdEmailMessage()
        msg["Subject"] = message.subject
        _, _, from_formatted = self._resolve_from(message)
        msg["From"] = from_formatted
        msg["To"] = ", ".join(message.to)

        if message.cc:
            msg["Cc"] = ", ".join(message.cc)
        if message.bcc:
            msg["Bcc"] = ", ".join(message.bcc)
        if message.reply_to:
            msg["Reply-To"] = ", ".join(message.reply_to)

        for key, value in message.headers.items():
            msg[key] = value

        # Set plain text body
        msg.set_content(message.body)

        # Add HTML alternative if present
        for content, mimetype in message.alternatives:
            if mimetype == "text/html":
                msg.add_alternative(content, subtype="html")

        # Add attachments
        for filename, attach_content, mimetype in message.attachments:
            maintype, subtype = mimetype.split("/", 1)
            msg.add_attachment(
                attach_content,
                maintype=maintype,
                subtype=subtype,
                filename=filename,
            )

        return msg
