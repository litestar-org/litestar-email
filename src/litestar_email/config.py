from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from litestar.datastructures import State

    from litestar_email.backends.base import BaseEmailBackend
    from litestar_email.service import EmailService
    from litestar_email.transports.base import HTTPTransport

__all__ = (
    "AsyncServiceProvider",
    "BackendConfig",
    "EmailConfig",
    "MailgunConfig",
    "ResendConfig",
    "SESConfig",
    "SMTPConfig",
    "SendGridConfig",
)


class AsyncServiceProvider:
    """Provides EmailService as an async context manager.

    This class enables managed usage of the email service with automatic
    connection handling:

    Example::

        async with config.provide_service() as mailer:
            await mailer.send_message(message)
    """

    __slots__ = ("_config", "_service")

    def __init__(self, config: "EmailConfig") -> None:
        """Initialize the service provider.

        Args:
            config: The email configuration.
        """
        self._config = config
        self._service: "EmailService | None" = None

    async def __aenter__(self) -> "EmailService":
        """Enter the async context and return an EmailService.

        Returns:
            An EmailService instance with an open backend connection.
        """
        from litestar_email.service import EmailService

        self._service = EmailService(self._config)
        await self._service.__aenter__()
        return self._service

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Exit the async context and close the backend connection.

        Args:
            exc_type: The exception type, if an exception was raised.
            exc_val: The exception value, if an exception was raised.
            exc_tb: The exception traceback, if an exception was raised.
        """
        if self._service is not None:
            await self._service.__aexit__(exc_type, exc_val, exc_tb)
            self._service = None

    async def __aiter__(self) -> AsyncIterator["EmailService"]:
        """Iterate over the service provider, yielding a single EmailService.

        This method enables compatibility with Litestar's DI system.

        Yields:
            An EmailService instance with an open backend connection.
        """
        async with self as service:
            yield service


@dataclass(slots=True)
class SMTPConfig:
    """Configuration for SMTP email backend.

    This configuration class defines the settings for connecting to an SMTP
    server for sending email.

    Example:
        Configure for a local Mailpit instance::

            config = SMTPConfig(host="localhost", port=1025)

        Configure for a production server with TLS::

            config = SMTPConfig(
                host="smtp.example.com",
                port=587,
                username="user@example.com",
                password="secret",
                use_tls=True,
            )
    """

    host: str = "localhost"
    port: int = 25
    username: str | None = None
    password: str | None = None
    use_tls: bool = False
    use_ssl: bool = False
    timeout: int = 30


@dataclass(slots=True)
class ResendConfig:
    """Configuration for Resend API email backend.

    This configuration class defines the settings for the Resend API
    email service (https://resend.com).

    Example:
        Configure with an API key::

            config = ResendConfig(api_key="re_123abc...")

        Use aiohttp transport::

            config = ResendConfig(
                api_key="re_123abc...",
                http_transport="aiohttp",
            )
    """

    api_key: str = ""
    timeout: int = 30
    http_transport: "str | type[HTTPTransport]" = "httpx"


@dataclass(slots=True)
class SendGridConfig:
    """Configuration for SendGrid API email backend.

    This configuration class defines the settings for the SendGrid API
    email service (https://sendgrid.com).

    Example:
        Configure with an API key::

            config = SendGridConfig(api_key="SG.xxx...")

        Use aiohttp transport::

            config = SendGridConfig(
                api_key="SG.xxx...",
                http_transport="aiohttp",
            )
    """

    api_key: str = ""
    timeout: int = 30
    http_transport: "str | type[HTTPTransport]" = "httpx"


@dataclass(slots=True)
class MailgunConfig:
    """Configuration for Mailgun API email backend.

    This configuration class defines the settings for the Mailgun API
    email service (https://mailgun.com).

    Example:
        Configure with API key and domain::

            config = MailgunConfig(
                api_key="key-xxx...",
                domain="mg.example.com",
            )

        Configure for EU region::

            config = MailgunConfig(
                api_key="key-xxx...",
                domain="mg.example.com",
                region="eu",
            )

        Use aiohttp transport::

            config = MailgunConfig(
                api_key="key-xxx...",
                domain="mg.example.com",
                http_transport="aiohttp",
            )
    """

    api_key: str = ""
    domain: str = ""
    region: str = "us"
    timeout: int = 30
    http_transport: "str | type[HTTPTransport]" = "httpx"


@dataclass(slots=True)
class SESConfig:
    """Configuration for Amazon SES API email backend.

    This configuration class defines the settings for the Amazon SES API
    email service (https://aws.amazon.com/ses/).

    Example:
        Configure with explicit credentials::

            config = SESConfig(
                region="us-east-1",
                aws_access_key_id="AKIA...",
                aws_secret_access_key="secret...",
            )

        Use aiohttp transport::

            config = SESConfig(
                region="us-east-1",
                http_transport="aiohttp",
            )
    """

    region: str = "us-east-1"
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_session_token: str | None = None
    timeout: int = 30
    http_transport: "str | type[HTTPTransport]" = "httpx"


BackendConfig = SMTPConfig | ResendConfig | SendGridConfig | MailgunConfig | SESConfig
"""Type alias for all backend configuration types."""


@dataclass(slots=True)
class EmailConfig:
    """Configuration for the EmailPlugin.

    This configuration class defines the settings for sending email
    within a Litestar application.

    Example:
        Basic configuration with console backend::

            config = EmailConfig(
                backend="console",
                from_email="noreply@example.com",
                from_name="My App",
            )

        Configuration with SMTP backend::

            config = EmailConfig(
                backend=SMTPConfig(
                    host="smtp.example.com",
                    port=587,
                    use_tls=True,
                ),
                from_email="noreply@example.com",
            )

        Configuration with Resend API backend::

            config = EmailConfig(
                backend=ResendConfig(api_key="re_123abc..."),
                from_email="noreply@example.com",
            )
    """

    backend: str | BackendConfig = "console"
    from_email: str = "noreply@localhost"
    from_name: str = ""
    fail_silently: bool = False
    email_service_dependency_key: str = "mailer"
    email_service_state_key: str = "mailer"

    @property
    def signature_namespace(self) -> dict[str, Any]:
        """Return the plugin's signature namespace.

        Returns:
            A string keyed dict of names to be added to the namespace for signature forward reference resolution.
        """
        from litestar_email.backends.base import BaseEmailBackend
        from litestar_email.message import EmailMessage, EmailMultiAlternatives
        from litestar_email.service import EmailService

        return {
            "BaseEmailBackend": BaseEmailBackend,
            "EmailConfig": EmailConfig,
            "EmailMessage": EmailMessage,
            "EmailMultiAlternatives": EmailMultiAlternatives,
            "EmailService": EmailService,
            "MailgunConfig": MailgunConfig,
            "ResendConfig": ResendConfig,
            "SESConfig": SESConfig,
            "SMTPConfig": SMTPConfig,
            "SendGridConfig": SendGridConfig,
        }

    @property
    def dependencies(self) -> dict[str, Any]:
        """Return dependency providers for the plugin.

        Returns:
            A mapping of dependency keys to providers for Litestar's DI system.
        """
        from litestar.di import Provide

        return {self.email_service_dependency_key: Provide(self.provide_service, sync_to_thread=False)}

    def get_service(self, state: "State | None" = None) -> "EmailService":
        """Return an EmailService for this configuration.

        Args:
            state: Optional application state to fetch a cached service instance or config.

        Returns:
            An EmailService instance.
        """
        from litestar_email.service import EmailService

        if state is not None and self.email_service_state_key in state:
            cached = state[self.email_service_state_key]
            if isinstance(cached, EmailService):
                return cached
            if isinstance(cached, EmailConfig):
                return EmailService(cached)

        return EmailService(self)

    def get_backend(
        self,
        fail_silently: bool | None = None,
    ) -> "BaseEmailBackend":
        """Return a backend instance configured for this EmailConfig.

        Args:
            fail_silently: Optional override for fail_silently behavior.

        Returns:
            A configured backend instance.
        """
        from litestar_email.backends import get_backend

        return get_backend(self.backend, fail_silently=fail_silently, config=self)

    def provide_service(self) -> AsyncServiceProvider:
        """Provide an EmailService instance.

        Returns a context manager that yields an EmailService with managed
        connection lifecycle.

        Example::

            async with config.provide_service() as mailer:
                await mailer.send_message(message)

        Returns:
            An AsyncServiceProvider that yields an EmailService instance.
        """
        return AsyncServiceProvider(self)
