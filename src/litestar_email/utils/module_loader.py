"""Module loading utilities for litestar-email.

Provides functions for ensuring optional dependencies are installed
before they are used. These functions raise MissingDependencyError
with helpful installation instructions when a dependency is missing.
"""

from litestar_email.exceptions import MissingDependencyError
from litestar_email.utils.dependencies import module_available

__all__ = (
    "ensure_aiohttp",
    "ensure_aiosmtplib",
    "ensure_botocore",
    "ensure_httpx",
)


def _require_dependency(
    module_name: str,
    *,
    package_name: str | None = None,
    install_package: str | None = None,
) -> None:
    """Raise MissingDependencyError when an optional dependency is absent.

    Args:
        module_name: The module to check for (e.g., "httpx").
        package_name: The package name to display in the error message.
            Defaults to module_name if not provided.
        install_package: The optional dependency extra name to suggest
            for installation. Defaults to package_name if not provided.

    Raises:
        MissingDependencyError: If the module is not available.
    """
    if module_available(module_name):
        return

    package = package_name or module_name
    install = install_package or package
    raise MissingDependencyError(package=package, install_package=install)


def ensure_httpx() -> None:
    """Ensure httpx is available for HTTP transports.

    Note:
        May raise ``MissingDependencyError`` if httpx is not installed.
        httpx is bundled with Litestar, so this should rarely fail
        in a properly configured Litestar application.
    """
    _require_dependency("httpx")


def ensure_aiohttp() -> None:
    """Ensure aiohttp is available for HTTP transports.

    Note:
        May raise ``MissingDependencyError`` if aiohttp is not installed.

    Example:
        Check before using aiohttp transport::

            from litestar_email.utils.module_loader import ensure_aiohttp

            ensure_aiohttp()
            from aiohttp import ClientSession
            # use aiohttp
    """
    _require_dependency("aiohttp")


def ensure_aiosmtplib() -> None:
    """Ensure aiosmtplib is available for SMTP backend.

    Note:
        May raise ``MissingDependencyError`` if aiosmtplib is not installed.

    Example:
        Check before using SMTP backend::

            from litestar_email.utils.module_loader import ensure_aiosmtplib

            ensure_aiosmtplib()
            import aiosmtplib
            # use aiosmtplib
    """
    _require_dependency("aiosmtplib", install_package="smtp")


def ensure_botocore() -> None:
    """Ensure botocore is available for Amazon SES backend.

    Note:
        May raise ``MissingDependencyError`` if botocore is not installed.

    Example:
        Check before using SES backend::

            from litestar_email.utils.module_loader import ensure_botocore

            ensure_botocore()
            import botocore
            # use botocore
    """
    _require_dependency("botocore", install_package="ses")
