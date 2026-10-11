"""Email backends — public re-exports.

Factory and registry logic lives in :mod:`litestar_email.backends.factory`.
"""

from litestar_email.backends.base import BaseEmailBackend
from litestar_email.backends.console import ConsoleBackend
from litestar_email.backends.factory import (
    email_backend,
    get_backend,
    get_backend_class,
    list_backends,
)
from litestar_email.backends.file import FileBackend
from litestar_email.backends.mailgun import MailgunBackend
from litestar_email.backends.memory import InMemoryBackend
from litestar_email.backends.resend import ResendBackend
from litestar_email.backends.sendgrid import SendGridBackend
from litestar_email.backends.ses import SESBackend
from litestar_email.backends.smtp import SMTPBackend

__all__ = (
    "BaseEmailBackend",
    "ConsoleBackend",
    "FileBackend",
    "InMemoryBackend",
    "MailgunBackend",
    "ResendBackend",
    "SESBackend",
    "SMTPBackend",
    "SendGridBackend",
    "email_backend",
    "get_backend",
    "get_backend_class",
    "list_backends",
)
