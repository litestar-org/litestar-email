"""Tests for Amazon SES email backend."""

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from litestar_email.backends.ses import SESBackend
from litestar_email.config import SESConfig
from litestar_email.exceptions import (
    EmailAuthenticationError,
    EmailDeliveryError,
    EmailRateLimitError,
    MissingDependencyError,
)
from litestar_email.message import EmailMessage, EmailMultiAlternatives

pytestmark = pytest.mark.anyio


class _DummyAuth:
    """Stand-in for botocore.auth.SigV4Auth that records the body it signs."""

    __slots__ = ("captured_body",)

    def __init__(self) -> None:
        self.captured_body: bytes | None = None

    def add_auth(self, request: Any) -> None:
        self.captured_body = request.data
        request.headers["Authorization"] = "AWS4-HMAC-SHA256 ..."
        request.headers["X-Amz-Date"] = "20260101T000000Z"


class _DummyRequest:
    """Stand-in for botocore.awsrequest.AWSRequest."""

    __slots__ = ("data", "headers", "method", "url")

    def __init__(self, *, method: str, url: str, data: bytes) -> None:
        self.method = method
        self.url = url
        self.data = data
        self.headers: dict[str, str] = {}


def _build_mock_response(
    status_code: int = 200,
    text: str = "{}",
    headers: dict[str, str] | None = None,
) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.text = AsyncMock(return_value=text)
    response.get_header = MagicMock(side_effect=lambda name, default=None: (headers or {}).get(name, default))
    return response


async def test_ses_backend_requires_botocore(monkeypatch: pytest.MonkeyPatch) -> None:
    """SESBackend raises MissingDependencyError if botocore not installed."""
    from litestar_email.utils import dependencies

    monkeypatch.setattr(dependencies, "_dependency_cache", {"botocore": False})

    with pytest.raises(MissingDependencyError, match="botocore"):
        SESBackend()


async def test_ses_send_signs_and_transmits_identical_bytes() -> None:
    """The bytes signed by SigV4 must equal the bytes transmitted on the wire."""
    auth = _DummyAuth()
    config = SESConfig(region="us-east-1", aws_access_key_id="k", aws_secret_access_key="s")
    message = EmailMessage(
        to=["recipient@example.com"],
        subject="Hello",
        body="Plain text",
        from_email="sender@example.com",
    )

    mock_transport = AsyncMock()
    mock_transport.post = AsyncMock(return_value=_build_mock_response(200))

    with (
        patch("litestar_email.transports.get_transport", return_value=mock_transport),
        patch("botocore.auth.SigV4Auth", return_value=auth),
        patch("botocore.awsrequest.AWSRequest", side_effect=_DummyRequest),
        patch("botocore.credentials.Credentials"),
    ):
        async with SESBackend(config=config) as backend:
            sent = await backend.send_messages([message])

    assert sent == 1
    mock_transport.post.assert_called_once()
    kwargs = mock_transport.post.call_args.kwargs
    transmitted: bytes = kwargs["content"]
    assert transmitted == auth.captured_body, "signed body must match transmitted body byte-for-byte"

    payload = json.loads(transmitted)
    assert payload["FromEmailAddress"] == "sender@example.com"
    assert payload["Destination"] == {"ToAddresses": ["recipient@example.com"]}
    assert payload["Content"]["Simple"]["Subject"] == {"Data": "Hello"}
    assert payload["Content"]["Simple"]["Body"]["Text"] == {"Data": "Plain text"}

    headers = kwargs["headers"]
    assert headers["Authorization"].startswith("AWS4-HMAC-SHA256")
    assert headers["Content-Type"] == "application/json"


async def test_ses_send_includes_html_cc_bcc_reply_to() -> None:
    """Optional fields (HTML, CC, BCC, Reply-To) are placed in the SES v2 schema."""
    config = SESConfig(region="eu-west-1", aws_access_key_id="k", aws_secret_access_key="s")
    message = EmailMultiAlternatives(
        to=["a@example.com"],
        subject="Subject",
        body="Plain",
        html_body="<p>Hi</p>",
        cc=["cc@example.com"],
        bcc=["bcc@example.com"],
        reply_to=["reply@example.com"],
        from_email="sender@example.com",
    )

    mock_transport = AsyncMock()
    mock_transport.post = AsyncMock(return_value=_build_mock_response(200))

    with (
        patch("litestar_email.transports.get_transport", return_value=mock_transport),
        patch("botocore.auth.SigV4Auth", return_value=_DummyAuth()),
        patch("botocore.awsrequest.AWSRequest", side_effect=_DummyRequest),
        patch("botocore.credentials.Credentials"),
    ):
        async with SESBackend(config=config) as backend:
            await backend.send_messages([message])

    posted_url = mock_transport.post.call_args.args[0]
    assert posted_url == "https://email.eu-west-1.amazonaws.com/v2/email/outbound-emails"

    payload = json.loads(mock_transport.post.call_args.kwargs["content"])
    assert payload["Destination"]["CcAddresses"] == ["cc@example.com"]
    assert payload["Destination"]["BccAddresses"] == ["bcc@example.com"]
    assert payload["ReplyToAddresses"] == ["reply@example.com"]
    assert payload["Content"]["Simple"]["Body"]["Html"] == {"Data": "<p>Hi</p>"}
    assert payload["Content"]["Simple"]["Body"]["Text"] == {"Data": "Plain"}


async def test_ses_send_uses_default_credential_chain_when_keys_omitted() -> None:
    """When no explicit keys are configured, fall back to botocore's session credentials."""
    config = SESConfig(region="us-east-1")
    message = EmailMessage(to=["r@example.com"], subject="s", body="b", from_email="from@example.com")

    mock_transport = AsyncMock()
    mock_transport.post = AsyncMock(return_value=_build_mock_response(200))

    fake_session = MagicMock()
    fake_session.get_credentials = MagicMock(return_value=MagicMock())

    with (
        patch("litestar_email.transports.get_transport", return_value=mock_transport),
        patch("botocore.auth.SigV4Auth", return_value=_DummyAuth()),
        patch("botocore.awsrequest.AWSRequest", side_effect=_DummyRequest),
        patch("botocore.credentials.Credentials") as creds,
        patch("botocore.session.get_session", return_value=fake_session) as get_session,
    ):
        async with SESBackend(config=config) as backend:
            await backend.send_messages([message])

    creds.assert_not_called()
    get_session.assert_called_once()
    fake_session.get_credentials.assert_called_once()


async def test_ses_send_rate_limited_raises_with_retry_after() -> None:
    """A 429 response surfaces as EmailRateLimitError with retry_after parsed."""
    config = SESConfig(region="us-east-1", aws_access_key_id="k", aws_secret_access_key="s")
    message = EmailMessage(to=["r@example.com"], subject="s", body="b", from_email="from@example.com")

    mock_transport = AsyncMock()
    mock_transport.post = AsyncMock(
        return_value=_build_mock_response(status_code=429, text="too fast", headers={"Retry-After": "42"}),
    )

    with (
        patch("litestar_email.transports.get_transport", return_value=mock_transport),
        patch("botocore.auth.SigV4Auth", return_value=_DummyAuth()),
        patch("botocore.awsrequest.AWSRequest", side_effect=_DummyRequest),
        patch("botocore.credentials.Credentials"),
    ):
        async with SESBackend(config=config) as backend:
            with pytest.raises(EmailRateLimitError) as excinfo:
                await backend.send_messages([message])

    assert excinfo.value.retry_after == 42


async def test_ses_send_authentication_error_on_403() -> None:
    """A 403 response surfaces as EmailAuthenticationError."""
    config = SESConfig(region="us-east-1", aws_access_key_id="k", aws_secret_access_key="s")
    message = EmailMessage(to=["r@example.com"], subject="s", body="b", from_email="from@example.com")

    mock_transport = AsyncMock()
    mock_transport.post = AsyncMock(return_value=_build_mock_response(status_code=403, text="bad signature"))

    with (
        patch("litestar_email.transports.get_transport", return_value=mock_transport),
        patch("botocore.auth.SigV4Auth", return_value=_DummyAuth()),
        patch("botocore.awsrequest.AWSRequest", side_effect=_DummyRequest),
        patch("botocore.credentials.Credentials"),
    ):
        async with SESBackend(config=config) as backend:
            with pytest.raises(EmailAuthenticationError, match="bad signature"):
                await backend.send_messages([message])


async def test_ses_send_generic_4xx_raises_email_delivery_error() -> None:
    """A non-429/403 4xx response raises EmailDeliveryError with status echoed."""
    config = SESConfig(region="us-east-1", aws_access_key_id="k", aws_secret_access_key="s")
    message = EmailMessage(to=["r@example.com"], subject="s", body="b", from_email="from@example.com")

    mock_transport = AsyncMock()
    mock_transport.post = AsyncMock(return_value=_build_mock_response(status_code=400, text="invalid request"))

    with (
        patch("litestar_email.transports.get_transport", return_value=mock_transport),
        patch("botocore.auth.SigV4Auth", return_value=_DummyAuth()),
        patch("botocore.awsrequest.AWSRequest", side_effect=_DummyRequest),
        patch("botocore.credentials.Credentials"),
    ):
        async with SESBackend(config=config) as backend:
            with pytest.raises(EmailDeliveryError, match="400"):
                await backend.send_messages([message])


async def test_ses_send_rejects_attachments_loudly() -> None:
    """Attachments require Raw content and must not be silently dropped."""
    config = SESConfig(region="us-east-1", aws_access_key_id="k", aws_secret_access_key="s")
    message = EmailMessage(
        to=["r@example.com"],
        subject="s",
        body="b",
        from_email="from@example.com",
        attachments=[("file.txt", b"hi", "text/plain")],
    )

    with (
        patch("litestar_email.transports.get_transport", return_value=AsyncMock()),
        patch("botocore.auth.SigV4Auth", return_value=_DummyAuth()),
        patch("botocore.awsrequest.AWSRequest", side_effect=_DummyRequest),
        patch("botocore.credentials.Credentials"),
    ):
        async with SESBackend(config=config) as backend:
            with pytest.raises(EmailDeliveryError, match="attachments"):
                await backend.send_messages([message])


async def test_ses_send_rejects_empty_body() -> None:
    """A message with no text and no HTML alternative is rejected before signing."""
    config = SESConfig(region="us-east-1", aws_access_key_id="k", aws_secret_access_key="s")
    message = EmailMessage(to=["r@example.com"], subject="s", body="", from_email="from@example.com")

    with (
        patch("litestar_email.transports.get_transport", return_value=AsyncMock()),
        patch("botocore.auth.SigV4Auth", return_value=_DummyAuth()),
        patch("botocore.awsrequest.AWSRequest", side_effect=_DummyRequest),
        patch("botocore.credentials.Credentials"),
    ):
        async with SESBackend(config=config) as backend:
            with pytest.raises(EmailDeliveryError, match="text body or an HTML alternative"):
                await backend.send_messages([message])


async def test_ses_send_fail_silently_swallows_delivery_errors() -> None:
    """fail_silently suppresses generic delivery errors but counts only successful sends."""
    config = SESConfig(region="us-east-1", aws_access_key_id="k", aws_secret_access_key="s")
    bad = EmailMessage(to=["r@example.com"], subject="s", body="b", from_email="from@example.com")
    good = EmailMessage(to=["ok@example.com"], subject="s", body="b", from_email="from@example.com")

    mock_transport = AsyncMock()
    mock_transport.post = AsyncMock(
        side_effect=[
            _build_mock_response(status_code=500, text="server error"),
            _build_mock_response(status_code=200),
        ],
    )

    with (
        patch("litestar_email.transports.get_transport", return_value=mock_transport),
        patch("botocore.auth.SigV4Auth", return_value=_DummyAuth()),
        patch("botocore.awsrequest.AWSRequest", side_effect=_DummyRequest),
        patch("botocore.credentials.Credentials"),
    ):
        async with SESBackend(config=config, fail_silently=True) as backend:
            sent = await backend.send_messages([bad, good])

    assert sent == 1


async def test_ses_send_empty_messages_returns_zero() -> None:
    """Calling send_messages with [] is a no-op."""
    config = SESConfig(region="us-east-1", aws_access_key_id="k", aws_secret_access_key="s")
    backend = SESBackend(config=config)
    assert await backend.send_messages([]) == 0
