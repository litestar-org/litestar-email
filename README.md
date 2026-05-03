# litestar-email

Email support for Litestar applications. This plugin provides a pluggable email backend
system for sending transactional emails with support for multiple providers.

## Installation

```bash
pip install litestar-email
```

For production backends, install with the appropriate extra:

```bash
# SMTP backend
pip install litestar-email[smtp]

# Amazon SES backend (adds botocore for SigV4 signing)
pip install litestar-email[ses]

# aiohttp transport (alternative to httpx for API backends)
pip install litestar-email[aiohttp]
```

> **Note**: API backends (Resend, SendGrid, Mailgun, SES) use `httpx` which is bundled with Litestar.
> No extra HTTP transport installation is needed. SES additionally requires the `[ses]` extra
> for AWS Signature Version 4 signing.

## Usage

```python
from litestar import Litestar
from litestar_email import EmailConfig, EmailPlugin

# Development: console output
config = EmailConfig(
    backend="console",
    from_email="noreply@example.com",
    from_name="My App",
)

app = Litestar(plugins=[EmailPlugin(config=config)])
```

For production, pass a backend config object directly:

```python
from litestar_email import EmailConfig, EmailPlugin, SMTPConfig

config = EmailConfig(
    backend=SMTPConfig(host="smtp.example.com", port=587, use_tls=True),
    from_email="noreply@example.com",
)

app = Litestar(plugins=[EmailPlugin(config=config)])
```

### Sending Email

```python
from litestar_email import EmailMessage

message = EmailMessage(
    subject="Welcome!",
    body="Thanks for signing up.",
    to=["user@example.com"],
)

async with config.provide_service() as mailer:
    await mailer.send_message(message)
```

If ``message.from_email`` is omitted, the service uses ``config.from_email`` and
``config.from_name`` as defaults.

### Dependency Injection

The plugin registers a ``mailer`` dependency for handlers by default:

```python
from litestar import get
from litestar_email import EmailMessage, EmailService

@get("/welcome/{email:str}")
async def send_welcome(email: str, mailer: EmailService) -> dict[str, str]:
    message = EmailMessage(
        subject="Welcome!",
        body="Thanks for signing up.",
        to=[email],
    )
    await mailer.send_message(message)
    return {"status": "sent"}
```

This works for both router handlers and controller methods the same way, since the dependency is registered on the app.

If you need a service outside of Litestar (e.g., for a worker), use
``config.get_service()`` for a one-off instance or ``config.provide_service()``
for batch sending.

### Events and Listeners

Event listeners in Litestar execute outside request context and cannot receive
DI-injected dependencies. Pass the mailer explicitly:

```python
from litestar import Litestar, get
from litestar.events import listener
from litestar_email import EmailConfig, EmailMessage, EmailPlugin, EmailService, SMTPConfig

config = EmailConfig(
    backend=SMTPConfig(host="localhost", port=1025),
    from_email="noreply@example.com",
    from_name="My App",
)

@get("/register/{email:str}")
async def register(email: str, mailer: EmailService) -> dict[str, str]:
    # Pass the DI-injected mailer to the event
    request.app.emit("user.registered", email, mailer=mailer)
    return {"status": "queued"}

@listener("user.registered")
async def on_user_registered(email: str, mailer: EmailService) -> None:
    # mailer is passed explicitly from emit(), not injected via DI
    await mailer.send_message(
        EmailMessage(subject="Welcome!", body="Thanks for signing up.", to=[email]),
    )

app = Litestar(
    plugins=[EmailPlugin(config=config)],
    listeners=[on_user_registered],
)
```

You can override the dependency and state keys via ``EmailConfig`` if needed:
``email_service_dependency_key="email_service"`` and ``email_service_state_key="email_service"``.

### Standalone (No Litestar)

Use the config helpers directly without Litestar:

```python
from litestar_email import EmailConfig, EmailMessage, SMTPConfig

config = EmailConfig(
    backend=SMTPConfig(host="localhost", port=1025),
    from_email="noreply@example.com",
)
message = EmailMessage(
    subject="Hello!",
    body="This is a standalone send.",
    to=["user@example.com"],
)

async with config.provide_service() as mailer:
    await mailer.send_message(message)
```

For batch sends, use the context manager to reuse the connection:

```python
async with config.provide_service() as mailer:
    await mailer.send_messages([message1, message2, message3])
```

### HTML Email

```python
from litestar_email import EmailMultiAlternatives

message = EmailMultiAlternatives(
    subject="Welcome!",
    body="Thanks for signing up.",  # Plain text fallback
    html_body="<h1>Welcome!</h1><p>Thanks for signing up.</p>",
    to=["user@example.com"],
)
```

## Available Backends

| Backend | Config Class | Use Case |
|---------|--------------|----------|
| `console` | - | Development (prints to stdout) |
| `memory` | - | Testing (stores in memory) |
| `smtp` | `SMTPConfig` | Production SMTP servers |
| `resend` | `ResendConfig` | Resend HTTP API |
| `sendgrid` | `SendGridConfig` | SendGrid HTTP API |
| `mailgun` | `MailgunConfig` | Mailgun HTTP API |
| `ses` | `SESConfig` | Amazon SES API v2 (SigV4-signed) |

API backends (Resend, SendGrid, Mailgun, SES) support configurable HTTP transports:

```python
from litestar_email import ResendConfig

# Default: uses httpx (bundled with Litestar)
config = ResendConfig(api_key="re_xxx...")

# Alternative: use aiohttp
config = ResendConfig(api_key="re_xxx...", http_transport="aiohttp")
```

## Testing

The `InMemoryBackend` is designed for testing:

```python
from litestar_email.backends import InMemoryBackend

def test_sends_welcome_email():
    InMemoryBackend.clear()

    # ... code that sends email ...

    assert len(InMemoryBackend.outbox) == 1
    assert InMemoryBackend.outbox[0].subject == "Welcome!"
```

If you need direct backend access in tests, use ``config.get_backend()``:

```python
from litestar_email import EmailConfig, EmailMessage

config = EmailConfig(backend="memory")
backend = config.get_backend()

message = EmailMessage(subject="Hello", body="Body", to=["user@example.com"])
await backend.send_messages([message])
```

## Development

```bash
make install    # Install dependencies
make test       # Run tests
make lint       # Run linting
make check-all  # Run all checks
```

## License

MIT
