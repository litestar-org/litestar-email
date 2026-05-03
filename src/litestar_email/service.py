from typing import TYPE_CHECKING

from typing_extensions import Self

from litestar_email.backends import BaseEmailBackend

if TYPE_CHECKING:
    from litestar_email.config import EmailConfig
    from litestar_email.message import EmailMessage

__all__ = ("EmailService",)


class EmailService:
    """High-level helper for sending email with a configured backend.

    This service is intended for dependency injection in handlers. It can also
    be used directly or as an async context manager to reuse connections.
    Outside of a context manager, each send uses a fresh backend instance.
    """

    __slots__ = ("_backend", "_config")

    def __init__(self, config: "EmailConfig") -> None:
        """Initialize the email service.

        Args:
            config: The email configuration.
        """
        self._config = config
        self._backend: BaseEmailBackend | None = None

    @property
    def config(self) -> "EmailConfig":
        """Return the email configuration."""
        return self._config

    def get_backend(self) -> BaseEmailBackend:
        """Return a backend instance for the configured backend name.

        When the service is not in a context manager, this returns a new backend
        instance each call.
        """
        if self._backend is not None:
            return self._backend
        return self._config.get_backend()

    async def send_messages(self, messages: list["EmailMessage"]) -> int:
        """Send a list of email messages.

        Args:
            messages: List of EmailMessage instances.

        Returns:
            Number of messages sent.
        """
        if not messages:
            return 0

        if self._backend is not None:
            return await self._backend.send_messages(messages)

        backend = self._config.get_backend()
        try:
            await backend.open()
            return await backend.send_messages(messages)
        finally:
            await backend.close()

    async def send_message(self, message: "EmailMessage") -> int:
        """Send a single email message.

        Args:
            message: The email message to send.

        Returns:
            Number of messages sent (0 or 1).
        """
        return await self.send_messages([message])

    async def __aenter__(self) -> Self:
        if self._backend is None:
            self._backend = self._config.get_backend()
            await self._backend.open()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        if self._backend is not None:
            await self._backend.close()
            self._backend = None
