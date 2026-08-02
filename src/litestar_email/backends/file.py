"""File email backend — writes each message to a file on disk."""

import asyncio
import re
from datetime import datetime, timezone
from email.generator import BytesGenerator
from email.message import EmailMessage as StdEmailMessage
from email.policy import SMTP as SMTP_POLICY
from io import BytesIO, StringIO
from itertools import count
from pathlib import Path
from typing import TYPE_CHECKING

from litestar_email.backends.base import BaseEmailBackend
from litestar_email.backends.console import render_text_message
from litestar_email.exceptions import EmailDeliveryError

if TYPE_CHECKING:
    from litestar_email.config import FileConfig
    from litestar_email.message import EmailMessage

__all__ = ("FileBackend",)

_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")
_SLUG_MAX_LENGTH = 50
_SLUG_FALLBACK = "no-subject"


def _slugify(subject: str) -> str:
    """Slugify a subject for use in a filename.

    Lowercases, replaces non-alphanumeric runs with ``-``, strips
    leading/trailing ``-``, truncates to 50 characters, and falls back
    to ``no-subject`` when the result is empty.

    Args:
        subject: The email subject to slugify.

    Returns:
        A filesystem-safe slug.
    """
    slug = _SLUG_PATTERN.sub("-", subject.lower()).strip("-")
    if not slug:
        return _SLUG_FALLBACK
    return slug[:_SLUG_MAX_LENGTH].rstrip("-") or _SLUG_FALLBACK


def _write_bytes_exclusive(target: Path, payload: bytes) -> None:
    """Write bytes to ``target`` without overwriting an existing file."""
    with target.open("xb") as file:
        file.write(payload)


class FileBackend(BaseEmailBackend):
    """Email backend that writes each message to a file on disk.

    Intended for local development — same niche as :class:`ConsoleBackend`,
    but persistent and inspectable. Each message is written to its own file
    in :attr:`FileConfig.path`. The default ``.eml`` format opens directly
    in mail clients (Apple Mail, Thunderbird, VS Code preview); the
    ``"text"`` format produces output byte-identical to ``ConsoleBackend``.

    Example:
        Default ``.eml`` format::

            from litestar_email import EmailConfig, FileConfig

            config = EmailConfig(
                backend=FileConfig(path="./tmp/emails"),
                from_email="noreply@example.com",
            )
    """

    __slots__ = ("_config", "_counter")

    def __init__(
        self,
        config: "FileConfig | None" = None,
        fail_silently: bool = False,
        default_from_email: str | None = None,
        default_from_name: str | None = None,
    ) -> None:
        """Initialize the file backend.

        Args:
            config: File backend configuration. If None, defaults to
                ``FileConfig(path="./emails")``.
            fail_silently: If True, suppress exceptions during send.
            default_from_email: Default sender email when message.from_email is missing.
            default_from_name: Default sender name when message.from_email has no name.
        """
        super().__init__(
            fail_silently=fail_silently,
            default_from_email=default_from_email,
            default_from_name=default_from_name,
        )

        if config is None:
            from litestar_email.config import FileConfig

            config = FileConfig()

        self._config = config
        self._counter = count(0)

    async def open(self) -> bool:
        """Create the output directory if it does not exist.

        Returns:
            Always True. Directory creation is idempotent.
        """
        await asyncio.to_thread(
            Path(self._config.path).mkdir,
            parents=True,
            exist_ok=True,
        )
        return True

    async def send_messages(self, messages: list["EmailMessage"]) -> int:
        """Write messages to disk.

        Args:
            messages: List of messages to write.

        Returns:
            The number of messages successfully written.

        Raises:
            EmailDeliveryError: If writing fails and ``fail_silently`` is False.
        """
        if not messages:
            return 0

        try:
            await self.open()
        except Exception as exc:
            if not self.fail_silently:
                msg = f"Failed to prepare file backend directory {self._config.path!r}"
                raise EmailDeliveryError(msg) from exc
            return 0

        num_sent = 0
        for message in messages:
            try:
                await self._write_message(message)
                num_sent += 1
            except Exception as exc:
                if not self.fail_silently:
                    msg = f"Failed to write email to {self._config.path!r}"
                    raise EmailDeliveryError(msg) from exc
        return num_sent

    async def _write_message(self, message: "EmailMessage") -> None:
        """Write a single message to its own file.

        Args:
            message: The email message to write.
        """
        if self._config.format == "eml":
            payload = self._build_eml_bytes(message)
        else:
            buffer = StringIO()
            render_text_message(message, resolve_from=self._resolve_from, stream=buffer)
            payload = buffer.getvalue().encode("utf-8")

        while True:
            filename = self._build_filename(message)
            target = Path(self._config.path) / filename
            try:
                await asyncio.to_thread(_write_bytes_exclusive, target, payload)
            except FileExistsError:
                continue
            else:
                return

    def _build_filename(self, message: "EmailMessage") -> str:
        """Build the filename for a message.

        Args:
            message: The email message.

        Returns:
            A filename of the form ``YYYYMMDD-HHMMSS-NNNNNN-<slug>.{eml,txt}``.
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        counter = f"{next(self._counter):06d}"
        slug = _slugify(message.subject)
        extension = "eml" if self._config.format == "eml" else "txt"
        return f"{timestamp}-{counter}-{slug}.{extension}"

    def _build_eml_bytes(self, message: "EmailMessage") -> bytes:
        """Build the RFC 822 (.eml) payload for a message.

        Args:
            message: The email message.

        Returns:
            Serialized message bytes using ``email.policy.SMTP``.
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

        msg.set_content(message.body)

        for content, mimetype in message.alternatives:
            if mimetype == "text/html":
                msg.add_alternative(content, subtype="html")

        for filename, attach_content, mimetype in message.attachments:
            maintype, subtype = mimetype.split("/", 1)
            msg.add_attachment(
                attach_content,
                maintype=maintype,
                subtype=subtype,
                filename=filename,
            )

        buffer = BytesIO()
        BytesGenerator(buffer, policy=SMTP_POLICY).flatten(msg)
        return buffer.getvalue()
