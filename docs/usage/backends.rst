Email Backends
==============

litestar-email provides multiple email backends for different use cases.
Most applications should use :class:`~litestar_email.service.EmailService` via
DI or ``EmailConfig.provide_service()`` and treat direct backend access as an
advanced/testing concern.

Available Backends
------------------

+--------------+--------------------+----------------------------------+
| Backend      | Config Class       | Use Case                         |
+==============+====================+==================================+
| ``console``  | None               | Development (prints to stdout)   |
+--------------+--------------------+----------------------------------+
| ``memory``   | None               | Testing (stores in memory)       |
+--------------+--------------------+----------------------------------+
| ``file``     | ``FileConfig``     | Development (writes files)       |
+--------------+--------------------+----------------------------------+
| ``smtp``     | ``SMTPConfig``     | Production SMTP servers          |
+--------------+--------------------+----------------------------------+
| ``resend``   | ``ResendConfig``   | Resend API (modern hosting)      |
+--------------+--------------------+----------------------------------+
| ``sendgrid`` | ``SendGridConfig`` | SendGrid API (enterprise)        |
+--------------+--------------------+----------------------------------+
| ``mailgun``  | ``MailgunConfig``  | Mailgun API (transactional)      |
+--------------+--------------------+----------------------------------+
| ``ses``      | ``SESConfig``      | Amazon SES API v2                |
+--------------+--------------------+----------------------------------+

.. note::

   API backends (Resend, SendGrid, Mailgun, SES) use ``httpx`` which is bundled
   with Litestar. No extra installation is needed for the transport. Optionally,
   you can use ``aiohttp`` as an alternative transport by installing
   ``litestar-email[aiohttp]``. The SES backend additionally requires
   ``litestar-email[ses]`` for AWS Signature Version 4 signing.

SMTP Backend
------------

The SMTP backend uses `aiosmtplib <https://aiosmtplib.readthedocs.io/>`_ for
async email delivery. It supports STARTTLS, implicit SSL, and authentication.

SMTP Installation
^^^^^^^^^^^^^^^^^

.. code-block:: bash

    pip install litestar-email[smtp]

SMTP Configuration
^^^^^^^^^^^^^^^^^^

.. code-block:: python

    from litestar_email import EmailConfig, SMTPConfig

    # Basic SMTP (no encryption, no auth)
    config = EmailConfig(
        backend=SMTPConfig(host="localhost", port=25),
        from_email="noreply@example.com",
    )

    # SMTP with STARTTLS (port 587)
    config = EmailConfig(
        backend=SMTPConfig(
            host="smtp.example.com",
            port=587,
            username="user@example.com",
            password="your-password",
            use_tls=True,  # STARTTLS
        ),
        from_email="noreply@example.com",
    )

    # SMTP with implicit SSL (port 465)
    config = EmailConfig(
        backend=SMTPConfig(
            host="smtp.example.com",
            port=465,
            username="user@example.com",
            password="your-password",
            use_ssl=True,  # Implicit SSL
        ),
        from_email="noreply@example.com",
    )

SMTPConfig Options
^^^^^^^^^^^^^^^^^^

+--------------+----------+---------+-----------------------------------+
| Option       | Type     | Default | Description                       |
+==============+==========+=========+===================================+
| ``host``     | str      | localhost | SMTP server hostname            |
+--------------+----------+---------+-----------------------------------+
| ``port``     | int      | 25      | SMTP server port                  |
+--------------+----------+---------+-----------------------------------+
| ``username`` | str|None | None    | Authentication username           |
+--------------+----------+---------+-----------------------------------+
| ``password`` | str|None | None    | Authentication password           |
+--------------+----------+---------+-----------------------------------+
| ``use_tls``  | bool     | False   | Enable STARTTLS after connecting  |
+--------------+----------+---------+-----------------------------------+
| ``use_ssl``  | bool     | False   | Use implicit SSL/TLS (port 465)   |
+--------------+----------+---------+-----------------------------------+
| ``timeout``  | int      | 30      | Connection timeout in seconds     |
+--------------+----------+---------+-----------------------------------+

File Backend
------------

The file backend writes each outgoing message to its own file in a target
directory. Intended for local development - same niche as the console
backend, but persistent and inspectable. Defaults to ``.eml`` output so
files open directly in Apple Mail, Thunderbird, or the built-in VS Code
preview; switch to ``format="text"`` for a console-style plain-text dump.

File Configuration
^^^^^^^^^^^^^^^^^^

.. code-block:: python

    from litestar_email import EmailConfig, FileConfig

    # RFC 822 .eml files (default) — open in any mail client
    config = EmailConfig(
        backend=FileConfig(path="./tmp/emails"),
        from_email="noreply@example.com",
    )

    # Plain-text dump — identical to the console backend output
    config = EmailConfig(
        backend=FileConfig(path="./tmp/emails", format="text"),
        from_email="noreply@example.com",
    )

The target directory is auto-created with ``parents=True`` on first send.
Each message produces one file named
``YYYYMMDD-HHMMSS-NNNNNN-<slug>.{eml,txt}`` where ``<slug>`` is derived from
the subject (lowercased, non-alphanumeric runs replaced with ``-``,
truncated to 50 characters; falls back to ``no-subject``).

FileConfig Options
^^^^^^^^^^^^^^^^^^

+------------+-------------------------------+-------------+-----------------------------------+
| Option     | Type                          | Default     | Description                       |
+============+===============================+=============+===================================+
| ``path``   | ``str | Path``                | ``"./emails"`` | Directory to write files to    |
+------------+-------------------------------+-------------+-----------------------------------+
| ``format`` | ``Literal["eml", "text"]``    | ``"eml"``   | Output format                     |
+------------+-------------------------------+-------------+-----------------------------------+

.. note::

   The per-backend counter that disambiguates filenames within the same
   second is in-process. If multiple workers write to the same directory
   they may share a clock second; use distinct paths per worker to avoid
   the slim collision risk on identical subjects.

Resend Backend
--------------

The Resend backend sends emails via `Resend's HTTP API <https://resend.com/>`_.
This is ideal for modern hosting platforms that block SMTP ports.

.. note::

   No extra installation needed. ``httpx`` is bundled with Litestar.

Resend Configuration
^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    from litestar_email import EmailConfig, ResendConfig

    config = EmailConfig(
        backend=ResendConfig(api_key="re_xxxxxxxxxxxxxxxxxxxxxxxxxx"),
        from_email="noreply@yourdomain.com",
    )

    # With aiohttp transport (requires litestar-email[aiohttp])
    config = EmailConfig(
        backend=ResendConfig(
            api_key="re_xxxxxxxxxxxxxxxxxxxxxxxxxx",
            http_transport="aiohttp",
        ),
        from_email="noreply@yourdomain.com",
    )

Get your API key at: https://resend.com/api-keys

ResendConfig Options
^^^^^^^^^^^^^^^^^^^^

+--------------------+------+---------+------------------------------------+
| Option             | Type | Default | Description                        |
+====================+======+=========+====================================+
| ``api_key``        | str  | ""      | Resend API key (re_xxx)            |
+--------------------+------+---------+------------------------------------+
| ``timeout``        | int  | 30      | HTTP request timeout               |
+--------------------+------+---------+------------------------------------+
| ``http_transport`` | str  | "httpx" | HTTP transport ("httpx", "aiohttp")|
+--------------------+------+---------+------------------------------------+

SendGrid Backend
----------------

The SendGrid backend sends emails via `SendGrid's v3 API <https://sendgrid.com/>`_.
This is suitable for enterprise email delivery at scale.

.. note::

   No extra installation needed. ``httpx`` is bundled with Litestar.

SendGrid Configuration
^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    from litestar_email import EmailConfig, SendGridConfig

    config = EmailConfig(
        backend=SendGridConfig(api_key="SG.xxxxxxxxxxxxxxxxxxxxxxxxxx"),
        from_email="noreply@yourdomain.com",
    )

Get your API key at: https://app.sendgrid.com/settings/api_keys

SendGridConfig Options
^^^^^^^^^^^^^^^^^^^^^^

+--------------------+------+---------+------------------------------------+
| Option             | Type | Default | Description                        |
+====================+======+=========+====================================+
| ``api_key``        | str  | ""      | SendGrid API key (SG.xxx)          |
+--------------------+------+---------+------------------------------------+
| ``timeout``        | int  | 30      | HTTP request timeout               |
+--------------------+------+---------+------------------------------------+
| ``http_transport`` | str  | "httpx" | HTTP transport ("httpx", "aiohttp")|
+--------------------+------+---------+------------------------------------+

Mailgun Backend
---------------

The Mailgun backend sends emails via `Mailgun's HTTP API <https://mailgun.com/>`_.
Mailgun is a popular transactional email service with good deliverability.

.. note::

   No extra installation needed. ``httpx`` is bundled with Litestar.

Mailgun Configuration
^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    from litestar_email import EmailConfig, MailgunConfig

    # US region (default)
    config = EmailConfig(
        backend=MailgunConfig(
            api_key="key-xxxxxxxxxxxxxxxxxxxxxxxxxx",
            domain="mg.yourdomain.com",
        ),
        from_email="noreply@yourdomain.com",
    )

    # EU region
    config = EmailConfig(
        backend=MailgunConfig(
            api_key="key-xxxxxxxxxxxxxxxxxxxxxxxxxx",
            domain="mg.yourdomain.com",
            region="eu",
        ),
        from_email="noreply@yourdomain.com",
    )

Get your API key at: https://app.mailgun.com/settings/api_security

MailgunConfig Options
^^^^^^^^^^^^^^^^^^^^^

+--------------------+------+---------+----------------------------------------+
| Option             | Type | Default | Description                            |
+====================+======+=========+========================================+
| ``api_key``        | str  | ""      | Mailgun API key (key-xxx)              |
+--------------------+------+---------+----------------------------------------+
| ``domain``         | str  | ""      | Mailgun sending domain                 |
+--------------------+------+---------+----------------------------------------+
| ``region``         | str  | "us"    | API region ("us" or "eu")              |
+--------------------+------+---------+----------------------------------------+
| ``timeout``        | int  | 30      | HTTP request timeout                   |
+--------------------+------+---------+----------------------------------------+
| ``http_transport`` | str  | "httpx" | HTTP transport ("httpx", "aiohttp")    |
+--------------------+------+---------+----------------------------------------+

Amazon SES Backend
------------------

The SES backend sends emails via `Amazon SES API v2
<https://docs.aws.amazon.com/ses/latest/APIReference-V2/API_SendEmail.html>`_.
It uses AWS Signature Version 4 (SigV4) for authentication, signing the exact
JSON bytes that are placed on the wire so signatures cannot be invalidated by
transport-level re-serialization.

SES Installation
^^^^^^^^^^^^^^^^

.. code-block:: bash

    pip install litestar-email[ses]

SES Configuration
^^^^^^^^^^^^^^^^^

.. code-block:: python

    from litestar_email import EmailConfig, SESConfig

    # Explicit IAM credentials
    config = EmailConfig(
        backend=SESConfig(
            region="us-east-1",
            aws_access_key_id="AKIA...",
            aws_secret_access_key="...",
        ),
        from_email="noreply@yourdomain.com",
    )

    # Default credential chain (env vars / IAM role / shared config)
    config = EmailConfig(
        backend=SESConfig(region="us-east-1"),
        from_email="noreply@yourdomain.com",
    )

.. note::

   The SES backend uses the ``Simple`` content type, which does not support
   attachments. Attempting to send an :class:`~litestar_email.message.EmailMessage`
   with attachments raises :class:`~litestar_email.exceptions.EmailDeliveryError`.
   For attachments, use the SMTP backend.

SESConfig Options
^^^^^^^^^^^^^^^^^

+-------------------------+-------------+-------------+-------------------------------------------+
| Option                  | Type        | Default     | Description                               |
+=========================+=============+=============+===========================================+
| ``region``              | str         | "us-east-1" | AWS region for the SES endpoint           |
+-------------------------+-------------+-------------+-------------------------------------------+
| ``aws_access_key_id``   | str \| None | None        | Optional explicit access key              |
+-------------------------+-------------+-------------+-------------------------------------------+
| ``aws_secret_access_key`` | str \| None | None      | Optional explicit secret key              |
+-------------------------+-------------+-------------+-------------------------------------------+
| ``aws_session_token``   | str \| None | None        | Optional session token (STS / IAM role)   |
+-------------------------+-------------+-------------+-------------------------------------------+
| ``timeout``             | int         | 30          | HTTP request timeout                      |
+-------------------------+-------------+-------------+-------------------------------------------+
| ``http_transport``      | str         | "httpx"     | HTTP transport ("httpx", "aiohttp")       |
+-------------------------+-------------+-------------+-------------------------------------------+

Error Handling
--------------

All backends raise consistent exceptions for error handling:

.. code-block:: python

    from litestar_email.exceptions import (
        EmailBackendError,      # Configuration/initialization errors
        EmailConnectionError,   # Connection failures
        EmailAuthenticationError,  # Auth failures
        EmailDeliveryError,     # Sending failures
        EmailRateLimitError,    # API rate limiting
    )

    try:
        await backend.send_messages([message])
    except EmailRateLimitError as e:
        # Wait and retry
        await asyncio.sleep(e.retry_after or 60)
    except EmailDeliveryError as e:
        # Log and handle delivery failure
        logger.error(f"Email delivery failed: {e}")
    except EmailConnectionError as e:
        # Handle connection issues
        logger.error(f"Cannot connect to email server: {e}")

Fail Silently
^^^^^^^^^^^^^

All backends support a ``fail_silently`` option that suppresses exceptions:

.. code-block:: python

    config = EmailConfig(
        backend=SMTPConfig(host="localhost", port=1025),
        fail_silently=True,  # Suppress sending errors
    )

    backend = config.get_backend()  # uses config.fail_silently

Connection Pooling
------------------

All backends support the async context manager protocol for connection pooling:

.. code-block:: python

    backend = get_backend("smtp", config=config)

    # Connection is opened and closed per call
    await backend.send_messages([message1])
    await backend.send_messages([message2])

    # Better: Reuse connection for multiple sends
    async with backend:
        await backend.send_messages([message1])
        await backend.send_messages([message2])
        await backend.send_messages([message3])

Custom Backends
---------------

You can implement your own backend by subclassing ``BaseEmailBackend`` and registering it:

.. code-block:: python

    from litestar_email.backends import BaseEmailBackend, email_backend
    from litestar_email.exceptions import EmailDeliveryError

    @email_backend("mybackend")
    class MyBackend(BaseEmailBackend):
        __slots__ = ("_client",)

        async def open(self) -> bool:
            if self._client is not None:
                return False
            self._client = await create_client()
            return True

        async def close(self) -> None:
            if self._client is not None:
                await self._client.aclose()
                self._client = None

        async def send_messages(self, messages: list["EmailMessage"]) -> int:
            if not messages:
                return 0
            new_connection = await self.open()
            try:
                sent = 0
                for message in messages:
                    try:
                        await self._send_message(message)
                        sent += 1
                    except Exception as exc:
                        if not self.fail_silently:
                            raise EmailDeliveryError("Failed to send email") from exc
                return sent
            finally:
                if new_connection:
                    await self.close()

Use ``config.get_backend("mybackend")`` once it is registered, or use the import path
``"your_module.MyBackend"`` directly without registration.

Optional Dependencies
^^^^^^^^^^^^^^^^^^^^^

If your backend uses an optional dependency, use the ``MissingDependencyError`` pattern:

.. code-block:: python

    from litestar_email.exceptions import MissingDependencyError
    from litestar_email.utils.module_loader import _require_dependency

    class MyBackend(BaseEmailBackend):
        def __init__(self, ...) -> None:
            # Raises MissingDependencyError with install instructions if missing
            _require_dependency("mypackage", install_package="mybackend")
            super().__init__(...)

Contributing a Backend (PR)
---------------------------

When submitting a backend to this repo, include:

- Implementation under ``src/litestar_email/backends/`` with ``__slots__`` and Google-style docstrings.
- Optional dependency guards (see above) and new extras in ``pyproject.toml``.
- Registration in ``src/litestar_email/backends/__init__.py`` if it is a built-in backend.
- Tests covering success + failure paths (mock external APIs where needed).
- Documentation updates (this page + README examples if applicable).

Quality checks:

- ``make test`` and ``make lint`` must pass
- 90%+ coverage on new modules
- No ``from __future__ import annotations`` and no ``Optional[T]`` (use ``T | None``)
