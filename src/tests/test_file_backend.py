"""Tests for file email backend."""

import email
import re
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

import pytest

pytestmark = pytest.mark.anyio


async def test_file_backend_creates_directory(tmp_path: Path) -> None:
    """Test that the backend auto-creates the target directory."""
    from litestar_email import EmailMessage, FileBackend, FileConfig

    target = tmp_path / "nested" / "deeper" / "emails"
    backend = FileBackend(config=FileConfig(path=target))
    message = EmailMessage(subject="Hello", body="Body", to=["user@example.com"])

    count = await backend.send_messages([message])

    assert count == 1
    assert target.is_dir()
    assert len(list(target.iterdir())) == 1


async def test_file_backend_eml_round_trip(tmp_path: Path) -> None:
    """Test that an .eml file round-trips through email.message_from_bytes."""
    from litestar_email import EmailMultiAlternatives, FileBackend, FileConfig

    backend = FileBackend(config=FileConfig(path=tmp_path, format="eml"))
    message = EmailMultiAlternatives(
        subject="Hello there",
        body="Plain text body content.",
        html_body="<h1>Hello there</h1><p>HTML body content.</p>",
        from_email="sender@example.com",
        to=["recipient@example.com"],
    )
    message.attach("notes.txt", b"hello from a file", "text/plain")

    await backend.send_messages([message])

    files = sorted(tmp_path.iterdir())  # noqa: ASYNC240
    assert len(files) == 1
    parsed = email.message_from_bytes(files[0].read_bytes())

    assert parsed["Subject"] == "Hello there"
    assert parsed["From"] == "sender@example.com"
    assert parsed["To"] == "recipient@example.com"

    html_part = None
    attachment_part = None
    plain_part = None
    for part in parsed.walk():
        if part.get_content_type() == "text/plain" and part.get_filename() is None:
            plain_part = part
        elif part.get_content_type() == "text/html":
            html_part = part
        elif part.get_filename() == "notes.txt":
            attachment_part = part

    assert plain_part is not None
    plain_bytes = plain_part.get_payload(decode=True)
    assert isinstance(plain_bytes, bytes)
    assert "Plain text body content." in plain_bytes.decode("utf-8")

    assert html_part is not None
    html_bytes = html_part.get_payload(decode=True)
    assert isinstance(html_bytes, bytes)
    assert "<h1>Hello there</h1>" in html_bytes.decode("utf-8")

    assert attachment_part is not None
    assert attachment_part.get_content_type() == "text/plain"
    assert attachment_part.get_payload(decode=True) == b"hello from a file"


async def test_file_backend_text_format_matches_console(tmp_path: Path) -> None:
    """Test that text-format output matches ConsoleBackend output byte-for-byte."""
    from litestar_email import EmailMessage, FileBackend, FileConfig
    from litestar_email.backends import ConsoleBackend

    message = EmailMessage(
        subject="Compare me",
        body="Plain body for comparison.",
        from_email="sender@example.com",
        to=["recipient@example.com"],
        cc=["cc@example.com"],
        reply_to=["reply@example.com"],
        headers={"X-Custom": "header"},
    )
    message.attach_alternative("<p>HTML</p>", "text/html")
    message.attach("file.txt", b"content", "text/plain")

    stream = StringIO()
    console_backend = ConsoleBackend(stream=stream)
    await console_backend.send_messages([message])
    console_output = stream.getvalue()

    file_backend = FileBackend(config=FileConfig(path=tmp_path, format="text"))
    await file_backend.send_messages([message])

    files = sorted(tmp_path.iterdir())  # noqa: ASYNC240
    assert len(files) == 1
    file_output = files[0].read_text(encoding="utf-8")

    assert file_output == console_output


async def test_file_backend_filename_pattern(tmp_path: Path) -> None:
    """Test that the produced filename matches the documented pattern."""
    from litestar_email import EmailMessage, FileBackend, FileConfig

    backend = FileBackend(config=FileConfig(path=tmp_path))
    message = EmailMessage(subject="Welcome Back!", body="Body", to=["user@example.com"])

    await backend.send_messages([message])

    files = list(tmp_path.iterdir())  # noqa: ASYNC240
    assert len(files) == 1
    filename = files[0].name
    assert re.match(r"^\d{8}-\d{6}-\d{6}-[a-z0-9-]+\.(eml|txt)$", filename), filename
    assert "welcome-back" in filename


async def test_file_backend_slug_fallback(tmp_path: Path) -> None:
    """Test that empty and non-ASCII subjects fall back to ``no-subject``."""
    from litestar_email import EmailMessage, FileBackend, FileConfig

    backend = FileBackend(config=FileConfig(path=tmp_path))

    await backend.send_messages([EmailMessage(subject="", body="b", to=["u@example.com"])])
    await backend.send_messages([EmailMessage(subject="!!! ✨ !!!", body="b", to=["u@example.com"])])

    files = sorted(tmp_path.iterdir())  # noqa: ASYNC240
    assert len(files) == 2
    for path in files:
        assert "no-subject" in path.name


async def test_file_backend_counter_increments(tmp_path: Path) -> None:
    """Test that the counter increments for messages in the same second."""
    from litestar_email import EmailMessage, FileBackend, FileConfig

    backend = FileBackend(config=FileConfig(path=tmp_path))
    messages = [
        EmailMessage(subject="One", body="b", to=["u@example.com"]),
        EmailMessage(subject="Two", body="b", to=["u@example.com"]),
    ]

    await backend.send_messages(messages)

    files = sorted(tmp_path.iterdir())  # noqa: ASYNC240
    assert len(files) == 2
    counters = [path.name.split("-")[2] for path in files]
    assert counters[0] == "000000"
    assert counters[1] == "000001"


async def test_file_backend_does_not_overwrite_when_service_recreates_backend(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that colliding filenames are retried instead of overwritten."""
    import litestar_email.backends.file as file_backend
    from litestar_email import EmailConfig, EmailMessage, FileConfig

    class FrozenDateTime:
        @classmethod
        def now(cls, tz: timezone | None = None) -> datetime:
            return datetime(2026, 1, 1, 12, 0, 0, tzinfo=tz)

    monkeypatch.setattr(file_backend, "datetime", FrozenDateTime)

    config = EmailConfig(backend=FileConfig(path=tmp_path), from_email="noreply@example.com")
    service = config.get_service()

    await service.send_message(EmailMessage(subject="Same", body="first", to=["u@example.com"]))
    await service.send_message(EmailMessage(subject="Same", body="second", to=["u@example.com"]))

    files = sorted(tmp_path.iterdir())  # noqa: ASYNC240

    assert [path.name for path in files] == [
        "20260101-120000-000000-same.eml",
        "20260101-120000-000001-same.eml",
    ]
    assert b"first" in files[0].read_bytes()
    assert b"second" in files[1].read_bytes()


async def test_file_backend_fail_silently(tmp_path: Path) -> None:
    """Test that fail_silently controls EmailDeliveryError propagation."""
    from litestar_email import EmailMessage, FileBackend, FileConfig
    from litestar_email.exceptions import EmailDeliveryError

    # Create a regular file then attempt to mkdir a path *inside* it,
    # which causes mkdir(parents=True) to fail with NotADirectoryError.
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory")
    bad_path = blocker / "subdir"

    message = EmailMessage(subject="Fail", body="b", to=["u@example.com"])

    strict = FileBackend(config=FileConfig(path=bad_path), fail_silently=False)
    with pytest.raises(EmailDeliveryError):
        await strict.send_messages([message])

    silent = FileBackend(config=FileConfig(path=bad_path), fail_silently=True)
    count = await silent.send_messages([message])
    assert count == 0


async def test_file_backend_writes_txt_extension_for_text_format(tmp_path: Path) -> None:
    """Test that format=text produces ``.txt`` files."""
    from litestar_email import EmailMessage, FileBackend, FileConfig

    backend = FileBackend(config=FileConfig(path=tmp_path, format="text"))
    message = EmailMessage(subject="Plain", body="Body", to=["user@example.com"])

    await backend.send_messages([message])

    files = list(tmp_path.iterdir())  # noqa: ASYNC240
    assert len(files) == 1
    assert files[0].suffix == ".txt"


async def test_file_backend_default_config_uses_emails_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that FileBackend defaults to ``./emails`` when no config is provided."""
    from litestar_email import FileBackend
    from litestar_email.config import FileConfig

    monkeypatch.chdir(tmp_path)
    backend = FileBackend()
    assert isinstance(backend._config, FileConfig)
    assert backend._config.path == "./emails"
    assert backend._config.format == "eml"


async def test_file_backend_send_empty_list(tmp_path: Path) -> None:
    """Test that send_messages([]) returns 0 without writing or creating files."""
    from litestar_email import FileBackend, FileConfig

    target = tmp_path / "unused"
    backend = FileBackend(config=FileConfig(path=target))

    count = await backend.send_messages([])

    assert count == 0
    assert not target.exists()


async def test_file_backend_eml_includes_full_headers(tmp_path: Path) -> None:
    """Test that cc, bcc, reply_to, and custom headers are serialized in .eml output."""
    from litestar_email import EmailMessage, FileBackend, FileConfig

    backend = FileBackend(config=FileConfig(path=tmp_path))
    message = EmailMessage(
        subject="Headers",
        body="b",
        from_email="sender@example.com",
        to=["to@example.com"],
        cc=["cc@example.com"],
        bcc=["bcc@example.com"],
        reply_to=["reply@example.com"],
        headers={"X-Custom": "value"},
    )

    await backend.send_messages([message])

    files = sorted(tmp_path.iterdir())  # noqa: ASYNC240
    parsed = email.message_from_bytes(files[0].read_bytes())
    assert parsed["Cc"] == "cc@example.com"
    assert parsed["Bcc"] == "bcc@example.com"
    assert parsed["Reply-To"] == "reply@example.com"
    assert parsed["X-Custom"] == "value"


async def test_file_backend_write_failure_per_message(tmp_path: Path) -> None:
    """Test that a per-message write failure raises EmailDeliveryError when strict."""
    from litestar_email import EmailMessage, FileBackend, FileConfig
    from litestar_email.exceptions import EmailDeliveryError

    class BoomBackend(FileBackend):
        async def _write_message(self, message: EmailMessage) -> None:
            msg = "simulated write failure"
            raise OSError(msg)

    backend = BoomBackend(config=FileConfig(path=tmp_path))
    message = EmailMessage(subject="Fail", body="b", to=["u@example.com"])

    with pytest.raises(EmailDeliveryError, match="Failed to write"):
        await backend.send_messages([message])

    silent = BoomBackend(config=FileConfig(path=tmp_path), fail_silently=True)
    count = await silent.send_messages([message])
    assert count == 0
