import sys
from typing import TYPE_CHECKING, TextIO

from litestar_email.backends.base import BaseEmailBackend

if TYPE_CHECKING:
    from collections.abc import Callable

    from litestar_email.message import EmailMessage

__all__ = ("ConsoleBackend", "render_text_message")


def render_text_message(
    message: "EmailMessage",
    *,
    resolve_from: "Callable[[EmailMessage], tuple[str, str, str]]",
    stream: TextIO,
) -> None:
    """Write a console-style plain-text rendering of a message to ``stream``.

    Shared by :class:`ConsoleBackend` and the file backend's ``format="text"``
    output so the two stay identical for the same message.

    Args:
        message: The email message to render.
        resolve_from: Callable returning ``(email, name, formatted)`` for the
            message's sender, typically ``backend._resolve_from``.
        stream: A text stream to write to.
    """
    separator = "-" * 60
    stream.write(f"{separator}\n")
    stream.write(f"Subject: {message.subject}\n")
    _, _, from_formatted = resolve_from(message)
    stream.write(f"From: {from_formatted}\n")
    stream.write(f"To: {', '.join(message.to)}\n")

    if message.cc:
        stream.write(f"Cc: {', '.join(message.cc)}\n")

    if message.bcc:
        stream.write(f"Bcc: {', '.join(message.bcc)}\n")

    if message.reply_to:
        stream.write(f"Reply-To: {', '.join(message.reply_to)}\n")

    if message.headers:
        stream.writelines(f"{key}: {value}\n" for key, value in message.headers.items())

    stream.write(f"\n{message.body}\n")

    for content, mimetype in message.alternatives:
        stream.write(f"\n--- Alternative ({mimetype}) ---\n")
        stream.write(f"{content}\n")

    if message.attachments:
        stream.write("\nAttachments:\n")
        for filename, _, mimetype in message.attachments:
            stream.write(f"  - {filename} ({mimetype})\n")

    stream.write(f"{separator}\n\n")


class ConsoleBackend(BaseEmailBackend):
    """Email backend that writes messages to a stream (default: stdout).

    Useful for local development and debugging. Prints email metadata
    and content to the console in a human-readable format.

    Example:
        Basic configuration::

            from litestar_email import EmailConfig

            config = EmailConfig(backend="console")
    """

    __slots__ = ("stream",)

    def __init__(
        self,
        fail_silently: bool = False,
        stream: TextIO | None = None,
        default_from_email: str | None = None,
        default_from_name: str | None = None,
    ) -> None:
        """Initialize the console backend.

        Args:
            fail_silently: If True, exceptions are suppressed.
            stream: Output stream. Defaults to sys.stdout.
            default_from_email: Default sender email when message.from_email is missing.
            default_from_name: Default sender name when message.from_email has no name.
        """
        super().__init__(
            fail_silently=fail_silently,
            default_from_email=default_from_email,
            default_from_name=default_from_name,
        )
        self.stream = stream or sys.stdout

    async def send_messages(self, messages: list["EmailMessage"]) -> int:
        """Write email messages to the stream.

        Args:
            messages: List of messages to output.

        Returns:
            The number of messages written.
        """
        count = 0
        for message in messages:
            self._write_message(message)
            count += 1
        return count

    def _write_message(self, message: "EmailMessage") -> None:
        """Write a single message to the stream.

        Args:
            message: The email message to write.
        """
        render_text_message(message, resolve_from=self._resolve_from, stream=self.stream)
        self.stream.flush()
