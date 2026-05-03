from functools import lru_cache
from importlib import import_module
from inspect import signature
from typing import TYPE_CHECKING, Any

from litestar_email.backends.base import BaseEmailBackend

if TYPE_CHECKING:
    from litestar_email.config import BackendConfig, EmailConfig

__all__ = (
    "BaseEmailBackend",
    "ConsoleBackend",
    "InMemoryBackend",
    "MailgunBackend",
    "ResendBackend",
    "SESBackend",
    "SMTPBackend",
    "SendGridBackend",
    "get_backend",
    "get_backend_class",
    "list_backends",
    "register_backend",
)

# Global registry of backend short names to classes
_backend_registry: dict[str, type[BaseEmailBackend]] = {}


def register_backend(name: str) -> "type[BaseEmailBackend]":
    """Decorator to register a backend class with a short name.

    Args:
        name: The short name for the backend (e.g., "console", "smtp").

    Returns:
        A decorator that registers the backend class.

    Example:
        Registering a custom backend::

            @register_backend("mybackend")
            class MyBackend(BaseEmailBackend):
                async def send_messages(self, messages):
                    ...
    """

    def decorator(cls: type[BaseEmailBackend]) -> type[BaseEmailBackend]:
        _backend_registry[name] = cls
        return cls

    return decorator  # type: ignore[return-value]


@lru_cache(maxsize=1)
def _register_builtins() -> None:
    """Register built-in backends. Called lazily to avoid import cycles.

    All backends can be imported regardless of whether their dependencies
    are installed. They will raise MissingDependencyError when instantiated
    if the required packages are not available.
    """
    from litestar_email.backends.console import ConsoleBackend
    from litestar_email.backends.mailgun import MailgunBackend
    from litestar_email.backends.memory import InMemoryBackend
    from litestar_email.backends.resend import ResendBackend
    from litestar_email.backends.sendgrid import SendGridBackend
    from litestar_email.backends.ses import SESBackend
    from litestar_email.backends.smtp import SMTPBackend

    _backend_registry.setdefault("console", ConsoleBackend)
    _backend_registry.setdefault("memory", InMemoryBackend)
    _backend_registry.setdefault("smtp", SMTPBackend)
    _backend_registry.setdefault("resend", ResendBackend)
    _backend_registry.setdefault("ses", SESBackend)
    _backend_registry.setdefault("sendgrid", SendGridBackend)
    _backend_registry.setdefault("mailgun", MailgunBackend)


def get_backend_class(backend_path: str) -> type[BaseEmailBackend]:
    """Get a backend class by short name or full import path.

    Args:
        backend_path: Either a registered short name (e.g., "console", "memory")
            or a full Python import path (e.g., "myapp.backends.CustomBackend").

    Returns:
        The backend class.

    Raises:
        ValueError: If the backend cannot be found.

    Example:
        Getting a backend class::

            # By short name
            cls = get_backend_class("console")

            # By full path
            cls = get_backend_class("litestar_email.backends.console.ConsoleBackend")
    """
    _register_builtins()

    # Check registry first
    if backend_path in _backend_registry:
        return _backend_registry[backend_path]

    # Try to import as a full path
    if "." not in backend_path:
        msg = f"Unknown backend: {backend_path!r}. Available: {list(_backend_registry.keys())}"
        raise ValueError(msg)

    module_path, class_name = backend_path.rsplit(".", 1)
    module = import_module(module_path)
    return getattr(module, class_name)  # type: ignore[no-any-return]


def _get_backend_name_for_config(backend_config: "BackendConfig") -> str:
    """Map a backend config object to its backend name.

    Args:
        backend_config: A backend configuration object.

    Returns:
        The backend name string.

    Raises:
        ValueError: If the config type is not recognized.
    """
    from litestar_email.config import MailgunConfig, ResendConfig, SendGridConfig, SESConfig, SMTPConfig

    config_to_backend: dict[type, str] = {
        SMTPConfig: "smtp",
        ResendConfig: "resend",
        SESConfig: "ses",
        SendGridConfig: "sendgrid",
        MailgunConfig: "mailgun",
    }

    for config_type, backend_name in config_to_backend.items():
        if isinstance(backend_config, config_type):
            return backend_name

    msg = f"Unknown backend config type: {type(backend_config).__name__}"
    raise ValueError(msg)


def get_backend(
    backend: "str | BackendConfig" = "console",
    fail_silently: bool | None = None,
    config: "EmailConfig | None" = None,
) -> BaseEmailBackend:
    """Get an instantiated backend by name or config object.

    Args:
        backend: Either a backend short name (e.g., "console", "smtp"), a full
            import path, or a backend config object (SMTPConfig, ResendConfig, etc.).
        fail_silently: Whether the backend should suppress exceptions. If None,
            uses config.fail_silently when config is provided.
        config: Optional EmailConfig to extract common settings from (from_email,
            from_name, fail_silently).

    Returns:
        An instantiated backend.

    Note:
        May raise ``MissingDependencyError`` if the backend requires a package
        that is not installed.

    Example:
        Basic usage::

            backend = get_backend("console")
            async with backend:
                await backend.send_messages([message])

        With config object::

            backend = get_backend(SMTPConfig(host="localhost", port=1025))

        From EmailConfig::

            config = EmailConfig(
                backend=ResendConfig(api_key="re_xxx..."),
                fail_silently=True,
            )
            backend = get_backend(config.backend, config=config)
    """
    # Determine backend class and config from the backend argument
    backend_config: Any = None
    if isinstance(backend, str):
        backend_class = get_backend_class(backend)
    else:
        # backend is a config object - determine the backend class from type
        backend_name = _get_backend_name_for_config(backend)
        backend_class = get_backend_class(backend_name)
        backend_config = backend

    # Extract common settings from EmailConfig if provided
    default_from_email: str | None = None
    default_from_name: str | None = None
    resolved_fail_silently = fail_silently if fail_silently is not None else False
    if config is not None:
        default_from_email = config.from_email
        default_from_name = config.from_name
        if fail_silently is None:
            resolved_fail_silently = config.fail_silently

    backend_kwargs: dict[str, Any] = {
        "fail_silently": resolved_fail_silently,
        "default_from_email": default_from_email,
        "default_from_name": default_from_name,
    }

    # Pass config to backend if it was found
    if backend_config is not None:
        backend_kwargs["config"] = backend_config

    init_signature = signature(backend_class.__init__)
    accepts_kwargs = any(param.kind == param.VAR_KEYWORD for param in init_signature.parameters.values())
    if not accepts_kwargs:
        backend_kwargs = {key: value for key, value in backend_kwargs.items() if key in init_signature.parameters}

    return backend_class(**backend_kwargs)


def list_backends() -> list[str]:
    """Return a list of registered backend short names.

    Returns:
        A list of backend names that can be used with get_backend().
    """
    _register_builtins()
    return list(_backend_registry.keys())


# Re-export backend classes for convenience
# Backends can be imported regardless of whether dependencies are installed.
# They raise MissingDependencyError on instantiation if dependencies are missing.
from litestar_email.backends.console import ConsoleBackend
from litestar_email.backends.mailgun import MailgunBackend
from litestar_email.backends.memory import InMemoryBackend
from litestar_email.backends.resend import ResendBackend
from litestar_email.backends.sendgrid import SendGridBackend
from litestar_email.backends.ses import SESBackend
from litestar_email.backends.smtp import SMTPBackend
