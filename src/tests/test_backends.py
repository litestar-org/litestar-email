from io import StringIO
from pathlib import Path

import pytest

pytestmark = pytest.mark.anyio


def test_list_backends() -> None:
    """Test that list_backends returns registered backends."""
    from litestar_email import list_backends

    backends = list_backends()
    assert "console" in backends
    assert "memory" in backends
    assert "file" in backends


def test_get_backend_class_by_name() -> None:
    """Test getting a backend class by short name."""
    from litestar_email import get_backend_class
    from litestar_email.backends import ConsoleBackend, InMemoryBackend

    assert get_backend_class("console") is ConsoleBackend
    assert get_backend_class("memory") is InMemoryBackend


def test_get_backend_class_by_path() -> None:
    """Test getting a backend class by full import path."""
    from litestar_email import get_backend_class
    from litestar_email.backends import ConsoleBackend

    cls = get_backend_class("litestar_email.backends.console.ConsoleBackend")
    assert cls is ConsoleBackend


def test_get_backend_class_unknown() -> None:
    """Test that unknown backend raises ValueError."""
    from litestar_email import get_backend_class

    with pytest.raises(ValueError, match="Unknown backend"):
        get_backend_class("unknown")


def test_get_backend_instance() -> None:
    """Test getting an instantiated backend."""
    from litestar_email import get_backend
    from litestar_email.backends import ConsoleBackend

    backend = get_backend("console")
    assert isinstance(backend, ConsoleBackend)
    assert backend.fail_silently is False


def test_get_backend_with_fail_silently() -> None:
    """Test backend respects fail_silently parameter."""
    from litestar_email import get_backend

    backend = get_backend("console", fail_silently=True)
    assert backend.fail_silently is True


def test_get_backend_uses_config_defaults() -> None:
    """Test that config defaults are applied to backend."""
    from litestar_email import get_backend
    from litestar_email.config import EmailConfig

    config = EmailConfig(
        backend="console",
        from_email="noreply@example.com",
        from_name="Litestar",
        fail_silently=True,
    )
    backend = get_backend("console", config=config)

    assert backend.fail_silently is True
    assert backend._default_from_email == "noreply@example.com"
    assert backend._default_from_name == "Litestar"


def test_config_get_backend_returns_backend() -> None:
    """Test EmailConfig.get_backend returns a backend instance."""
    from litestar_email.backends import InMemoryBackend
    from litestar_email.config import EmailConfig

    config = EmailConfig(backend="memory")
    backend = config.get_backend()

    assert isinstance(backend, InMemoryBackend)


def test_file_config_round_trip_through_factory(tmp_path: Path) -> None:
    """Test EmailConfig with FileConfig returns a configured FileBackend."""
    from litestar_email.backends import FileBackend
    from litestar_email.config import EmailConfig, FileConfig

    config = EmailConfig(
        backend=FileConfig(path=tmp_path),
        from_email="noreply@example.com",
        from_name="Litestar",
    )
    backend = config.get_backend()

    assert isinstance(backend, FileBackend)
    assert backend._config.path == tmp_path
    assert backend._default_from_email == "noreply@example.com"
    assert backend._default_from_name == "Litestar"


async def test_console_backend_sends_to_stream() -> None:
    """Test that ConsoleBackend writes to the stream."""
    from litestar_email import EmailMessage
    from litestar_email.backends import ConsoleBackend

    stream = StringIO()
    backend = ConsoleBackend(stream=stream)

    message = EmailMessage(
        subject="Test Subject",
        body="Test body",
        from_email="sender@example.com",
        to=["recipient@example.com"],
    )

    count = await backend.send_messages([message])
    assert count == 1

    output = stream.getvalue()
    assert "Test Subject" in output
    assert "sender@example.com" in output
    assert "recipient@example.com" in output
    assert "Test body" in output


async def test_memory_backend_stores_messages() -> None:
    """Test that InMemoryBackend stores messages in outbox."""
    from litestar_email import EmailMessage
    from litestar_email.backends import InMemoryBackend

    InMemoryBackend.clear()

    backend = InMemoryBackend()
    message = EmailMessage(
        subject="Test Subject",
        body="Test body",
        to=["recipient@example.com"],
    )

    count = await backend.send_messages([message])
    assert count == 1
    assert len(InMemoryBackend.outbox) == 1
    assert InMemoryBackend.outbox[0].subject == "Test Subject"


async def test_memory_backend_clear() -> None:
    """Test that InMemoryBackend.clear() empties the outbox."""
    from litestar_email import EmailMessage
    from litestar_email.backends import InMemoryBackend

    InMemoryBackend.clear()

    backend = InMemoryBackend()
    message = EmailMessage(subject="Test", body="Body", to=["test@example.com"])
    await backend.send_messages([message])

    assert len(InMemoryBackend.outbox) == 1
    InMemoryBackend.clear()
    assert len(InMemoryBackend.outbox) == 0


async def test_backend_context_manager() -> None:
    """Test that backends support async context manager protocol."""
    from litestar_email import EmailMessage
    from litestar_email.backends import InMemoryBackend

    InMemoryBackend.clear()

    message = EmailMessage(subject="Test", body="Body", to=["test@example.com"])

    async with InMemoryBackend() as backend:
        await backend.send_messages([message])

    assert len(InMemoryBackend.outbox) == 1


async def test_console_backend_with_alternatives() -> None:
    """Test that ConsoleBackend outputs alternative content."""
    from litestar_email import EmailMessage
    from litestar_email.backends import ConsoleBackend

    stream = StringIO()
    backend = ConsoleBackend(stream=stream)

    message = EmailMessage(
        subject="Test",
        body="Plain text",
        to=["test@example.com"],
    )
    message.attach_alternative("<h1>HTML</h1>", "text/html")

    await backend.send_messages([message])

    output = stream.getvalue()
    assert "text/html" in output
    assert "<h1>HTML</h1>" in output


async def test_console_backend_with_attachments() -> None:
    """Test that ConsoleBackend lists attachments."""
    from litestar_email import EmailMessage
    from litestar_email.backends import ConsoleBackend

    stream = StringIO()
    backend = ConsoleBackend(stream=stream)

    message = EmailMessage(
        subject="Test",
        body="Body",
        to=["test@example.com"],
    )
    message.attach("file.pdf", b"content", "application/pdf")

    await backend.send_messages([message])

    output = stream.getvalue()
    assert "file.pdf" in output
    assert "application/pdf" in output
