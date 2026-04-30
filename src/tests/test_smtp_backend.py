"""Tests for SMTP email backend."""

from unittest.mock import AsyncMock, MagicMock, patch

import aiosmtplib
import pytest

from litestar_email.utils import dependencies

pytestmark = pytest.mark.anyio


def test_smtp_backend_requires_aiosmtplib(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that SMTPBackend raises if aiosmtplib is not installed."""
    from litestar_email.exceptions import MissingDependencyError

    # Simulate aiosmtplib not being installed
    monkeypatch.setattr(dependencies, "_dependency_cache", {"aiosmtplib": False})

    # Need to reimport after patching the cache
    from litestar_email.backends.smtp import SMTPBackend

    with pytest.raises(MissingDependencyError, match="aiosmtplib"):
        SMTPBackend()


def test_smtp_backend_default_config() -> None:
    """Test SMTPBackend uses default config when none provided."""
    from litestar_email.backends.smtp import SMTPBackend

    backend = SMTPBackend()
    assert backend._config.host == "localhost"
    assert backend._config.port == 25
    assert backend._config.use_tls is False


def test_smtp_backend_custom_config() -> None:
    """Test SMTPBackend accepts custom config."""
    from litestar_email.backends.smtp import SMTPBackend
    from litestar_email.config import SMTPConfig

    config = SMTPConfig(
        host="smtp.example.com",
        port=587,
        username="user",
        password="pass",
        use_tls=True,
    )
    backend = SMTPBackend(config=config)
    assert backend._config.host == "smtp.example.com"
    assert backend._config.port == 587
    assert backend._config.use_tls is True


async def test_smtp_backend_open_returns_false_when_connected() -> None:
    """Test that open() returns False if already connected."""
    from litestar_email.backends.smtp import SMTPBackend

    backend = SMTPBackend()
    backend._connection = MagicMock()  # Simulate existing connection

    result = await backend.open()
    assert result is False


async def test_smtp_backend_close_when_not_connected() -> None:
    """Test that close() does nothing when not connected."""
    from litestar_email.backends.smtp import SMTPBackend

    backend = SMTPBackend()
    backend._connection = None

    # Should not raise
    await backend.close()


async def test_smtp_backend_send_empty_list() -> None:
    """Test sending empty list returns 0."""
    from litestar_email.backends.smtp import SMTPBackend

    backend = SMTPBackend()
    count = await backend.send_messages([])
    assert count == 0


async def test_smtp_backend_send_message_not_connected() -> None:
    """Test _send_message raises if not connected."""
    from litestar_email import EmailMessage
    from litestar_email.backends.smtp import SMTPBackend

    backend = SMTPBackend()
    backend._connection = None
    message = EmailMessage(subject="Test", body="Body", to=["test@example.com"])

    with pytest.raises(RuntimeError, match="SMTP connection not established"):
        await backend._send_message(message)


async def test_smtp_backend_builds_message_correctly() -> None:
    """Test _build_message creates proper EmailMessage."""
    from litestar_email import EmailMessage
    from litestar_email.backends.smtp import SMTPBackend

    backend = SMTPBackend()
    message = EmailMessage(
        subject="Test Subject",
        body="Plain text body",
        from_email="sender@example.com",
        to=["recipient@example.com"],
        cc=["cc@example.com"],
        bcc=["bcc@example.com"],
        reply_to=["reply@example.com"],
        headers={"X-Custom": "header"},
    )
    message.attach_alternative("<p>HTML body</p>", "text/html")
    message.attach("file.txt", b"content", "text/plain")

    result = backend._build_message(message)

    assert result["Subject"] == "Test Subject"
    assert result["From"] == "sender@example.com"
    assert result["To"] == "recipient@example.com"
    assert result["Cc"] == "cc@example.com"
    assert result["Bcc"] == "bcc@example.com"
    assert result["Reply-To"] == "reply@example.com"
    assert result["X-Custom"] == "header"


async def test_smtp_backend_uses_default_from() -> None:
    """Test default from values are applied when message lacks from_email."""
    from litestar_email import EmailMessage
    from litestar_email.backends.smtp import SMTPBackend

    backend = SMTPBackend(default_from_email="noreply@example.com", default_from_name="Litestar")
    message = EmailMessage(
        subject="Test Subject",
        body="Body",
        to=["recipient@example.com"],
    )

    result = backend._build_message(message)

    assert result["From"] == "Litestar <noreply@example.com>"


async def test_smtp_backend_with_mock_connection() -> None:
    """Test SMTPBackend sends messages via mocked connection."""
    from litestar_email import EmailMessage
    from litestar_email.backends.smtp import SMTPBackend

    backend = SMTPBackend()

    # Create mock connection
    mock_smtp = AsyncMock()
    mock_smtp.send_message = AsyncMock()

    backend._connection = mock_smtp

    message = EmailMessage(
        subject="Test",
        body="Body",
        to=["test@example.com"],
    )

    await backend._send_message(message)
    mock_smtp.send_message.assert_called_once()


async def test_smtp_backend_connection_error_silent() -> None:
    """Test connection error is suppressed when fail_silently=True."""
    from litestar_email.backends.smtp import SMTPBackend
    from litestar_email.config import SMTPConfig

    config = SMTPConfig(host="invalid.host", port=9999)
    backend = SMTPBackend(config=config, fail_silently=True)

    # Mock the SMTP class to raise an error
    with patch("aiosmtplib.SMTP") as mock_smtp_class:
        mock_smtp = AsyncMock()
        mock_smtp.connect = AsyncMock(side_effect=aiosmtplib.SMTPConnectError("Connection failed"))
        mock_smtp_class.return_value = mock_smtp

        result = await backend.open()
        assert result is False
        assert backend._connection is None


async def test_smtp_backend_connection_error_raises() -> None:
    """Test connection error raises when fail_silently=False."""
    from litestar_email.backends.smtp import SMTPBackend
    from litestar_email.config import SMTPConfig
    from litestar_email.exceptions import EmailConnectionError

    config = SMTPConfig(host="invalid.host", port=9999)
    backend = SMTPBackend(config=config, fail_silently=False)

    with patch("aiosmtplib.SMTP") as mock_smtp_class:
        mock_smtp = AsyncMock()
        mock_smtp.connect = AsyncMock(side_effect=aiosmtplib.SMTPConnectError("Connection failed"))
        mock_smtp_class.return_value = mock_smtp

        with pytest.raises(EmailConnectionError, match="Failed to connect"):
            await backend.open()


async def test_smtp_backend_auth_error_raises() -> None:
    """Test authentication error raises proper exception."""
    from litestar_email.backends.smtp import SMTPBackend
    from litestar_email.config import SMTPConfig
    from litestar_email.exceptions import EmailAuthenticationError

    config = SMTPConfig(
        host="localhost",
        port=587,
        username="user",
        password="wrong",
    )
    backend = SMTPBackend(config=config, fail_silently=False)

    with patch("aiosmtplib.SMTP") as mock_smtp_class:
        mock_smtp = AsyncMock()
        mock_smtp.connect = AsyncMock()
        mock_smtp.starttls = AsyncMock()
        mock_smtp.login = AsyncMock(side_effect=aiosmtplib.SMTPAuthenticationError(535, "Auth failed"))
        mock_smtp_class.return_value = mock_smtp

        with pytest.raises(EmailAuthenticationError, match="authentication failed"):
            await backend.open()


async def test_smtp_backend_close_with_connection() -> None:
    """Test close() properly closes connection."""
    from litestar_email.backends.smtp import SMTPBackend

    backend = SMTPBackend()
    mock_connection = AsyncMock()
    mock_connection.quit = AsyncMock()
    backend._connection = mock_connection

    await backend.close()

    mock_connection.quit.assert_called_once()
    assert backend._connection is None


async def test_smtp_backend_close_error_silent() -> None:
    """Test close() suppresses errors when fail_silently=True."""
    from litestar_email.backends.smtp import SMTPBackend

    backend = SMTPBackend(fail_silently=True)
    mock_connection = AsyncMock()
    mock_connection.quit = AsyncMock(side_effect=Exception("Quit failed"))
    backend._connection = mock_connection

    await backend.close()  # Should not raise
    assert backend._connection is None


async def test_smtp_backend_send_messages_with_connection_management() -> None:
    """Test send_messages properly manages connection lifecycle."""
    from litestar_email import EmailMessage
    from litestar_email.backends.smtp import SMTPBackend
    from litestar_email.config import SMTPConfig

    config = SMTPConfig(host="localhost", port=1025)
    backend = SMTPBackend(config=config)

    with patch("aiosmtplib.SMTP") as mock_smtp_class:
        mock_smtp = AsyncMock()
        mock_smtp.connect = AsyncMock()
        mock_smtp.send_message = AsyncMock()
        mock_smtp.quit = AsyncMock()
        mock_smtp_class.return_value = mock_smtp

        message = EmailMessage(
            subject="Test",
            body="Body",
            from_email="sender@example.com",
            to=["test@example.com"],
        )

        count = await backend.send_messages([message])

        assert count == 1
        mock_smtp.connect.assert_called_once()
        mock_smtp.send_message.assert_called_once()
        mock_smtp.quit.assert_called_once()


async def test_smtp_backend_delivery_error_raises() -> None:
    """Test delivery error raises EmailDeliveryError."""
    from litestar_email import EmailMessage
    from litestar_email.backends.smtp import SMTPBackend
    from litestar_email.config import SMTPConfig
    from litestar_email.exceptions import EmailDeliveryError

    config = SMTPConfig(host="localhost", port=1025)
    backend = SMTPBackend(config=config, fail_silently=False)

    with patch("aiosmtplib.SMTP") as mock_smtp_class:
        mock_smtp = AsyncMock()
        mock_smtp.connect = AsyncMock()
        mock_smtp.send_message = AsyncMock(side_effect=Exception("Send failed"))
        mock_smtp.quit = AsyncMock()
        mock_smtp_class.return_value = mock_smtp

        message = EmailMessage(
            subject="Test",
            body="Body",
            to=["test@example.com"],
        )

        with pytest.raises(EmailDeliveryError, match="Failed to send email"):
            await backend.send_messages([message])


async def test_smtp_backend_starttls_upgrade() -> None:
    """Test STARTTLS is called when use_tls=True and use_ssl=False."""
    from litestar_email.backends.smtp import SMTPBackend
    from litestar_email.config import SMTPConfig

    config = SMTPConfig(
        host="localhost",
        port=587,
        use_tls=True,
        use_ssl=False,
    )
    backend = SMTPBackend(config=config)

    with patch("aiosmtplib.SMTP") as mock_smtp_class:
        mock_smtp = AsyncMock()
        mock_smtp.connect = AsyncMock()
        mock_smtp.starttls = AsyncMock()
        mock_smtp_class.return_value = mock_smtp

        await backend.open()

        mock_smtp.starttls.assert_called_once()


async def test_smtp_backend_starttls_no_double_call() -> None:
    """Test that start_tls=False is passed to aiosmtplib to prevent double STARTTLS.

    Regression test for: SMTP STARTTLS executed twice causes
    'Connection already using TLS' error when aiosmtplib auto-detects
    STARTTLS support and litestar-email also calls starttls() manually.
    """
    from litestar_email.backends.smtp import SMTPBackend
    from litestar_email.config import SMTPConfig

    config = SMTPConfig(
        host="smtp.example.com",
        port=587,
        use_tls=True,
        use_ssl=False,
    )
    backend = SMTPBackend(config=config)

    with patch("aiosmtplib.SMTP") as mock_smtp_class:
        mock_smtp = AsyncMock()
        mock_smtp.connect = AsyncMock()
        mock_smtp.starttls = AsyncMock()
        mock_smtp_class.return_value = mock_smtp

        await backend.open()

        # Verify start_tls=False was passed to disable auto-STARTTLS
        mock_smtp_class.assert_called_once_with(
            hostname="smtp.example.com",
            port=587,
            timeout=30,
            use_tls=False,
            start_tls=False,
        )
        # Verify manual STARTTLS is still called exactly once
        mock_smtp.starttls.assert_called_once()


async def test_smtp_backend_ssl_does_not_call_starttls() -> None:
    """Test that implicit SSL (use_ssl=True) does not trigger manual STARTTLS."""
    from litestar_email.backends.smtp import SMTPBackend
    from litestar_email.config import SMTPConfig

    config = SMTPConfig(
        host="smtp.example.com",
        port=465,
        use_tls=False,
        use_ssl=True,
    )
    backend = SMTPBackend(config=config)

    with patch("aiosmtplib.SMTP") as mock_smtp_class:
        mock_smtp = AsyncMock()
        mock_smtp.connect = AsyncMock()
        mock_smtp.starttls = AsyncMock()
        mock_smtp_class.return_value = mock_smtp

        await backend.open()

        # use_tls=True in aiosmtplib means implicit SSL
        mock_smtp_class.assert_called_once_with(
            hostname="smtp.example.com",
            port=465,
            timeout=30,
            use_tls=True,
            start_tls=False,
        )
        # No manual STARTTLS for implicit SSL
        mock_smtp.starttls.assert_not_called()


async def test_smtp_backend_no_tls_no_ssl() -> None:
    """Test plain connection without TLS or SSL does not call starttls."""
    from litestar_email.backends.smtp import SMTPBackend
    from litestar_email.config import SMTPConfig

    config = SMTPConfig(
        host="localhost",
        port=25,
        use_tls=False,
        use_ssl=False,
    )
    backend = SMTPBackend(config=config)

    with patch("aiosmtplib.SMTP") as mock_smtp_class:
        mock_smtp = AsyncMock()
        mock_smtp.connect = AsyncMock()
        mock_smtp.starttls = AsyncMock()
        mock_smtp_class.return_value = mock_smtp

        await backend.open()

        mock_smtp_class.assert_called_once_with(
            hostname="localhost",
            port=25,
            timeout=30,
            use_tls=False,
            start_tls=False,
        )
        mock_smtp.starttls.assert_not_called()
