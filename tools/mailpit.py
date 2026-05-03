"""Mailpit container manager for email testing.

This module provides utilities for managing a Mailpit container for
integration testing of email functionality. Mailpit is a modern
fake SMTP server with a web UI and REST API.

Mailpit GitHub: https://github.com/axllent/mailpit
"""

import shutil
import subprocess
import time
from enum import Enum

from typing_extensions import Self

__all__ = (
    "MailpitContainer",
    "NoRuntimeAvailableError",
    "RuntimeType",
)

# Default configuration
DEFAULT_CONTAINER_NAME = "mailpit"
DEFAULT_SMTP_PORT = 1025
DEFAULT_WEB_PORT = 8025
DEFAULT_IMAGE = "axllent/mailpit"


class RuntimeType(str, Enum):
    """Container runtime types."""

    DOCKER = "docker"
    PODMAN = "podman"
    NONE = "none"


class NoRuntimeAvailableError(Exception):
    """Raised when no container runtime is detected."""


class MailpitContainer:
    """Manager for Mailpit container lifecycle.

    This class handles starting, stopping, and interacting with a Mailpit
    container for email testing. It automatically detects Docker or Podman
    as the container runtime.

    Attributes:
        container_name: Name of the container (default: "mailpit").
        smtp_port: Host port for SMTP server (default: 1025).
        web_port: Host port for web UI and API (default: 8025).
        image: Docker image to use (default: "axllent/mailpit").

    Example:
        Basic usage in tests::

            container = MailpitContainer()
            container.start()
            try:
                # Run email tests...
                pass
            finally:
                container.stop()

        As context manager::

            with MailpitContainer() as mailpit:
                # Run email tests
                config = SMTPConfig(
                    host=mailpit.smtp_host,
                    port=mailpit.smtp_port,
                )
                # Send emails and verify via API
                messages = mailpit.get_messages()
    """

    __slots__ = (
        "_runtime",
        "_runtime_type",
        "container_name",
        "image",
        "smtp_port",
        "web_port",
    )

    def __init__(
        self,
        container_name: str = DEFAULT_CONTAINER_NAME,
        smtp_port: int = DEFAULT_SMTP_PORT,
        web_port: int = DEFAULT_WEB_PORT,
        image: str = DEFAULT_IMAGE,
    ) -> None:
        """Initialize Mailpit container manager.

        Args:
            container_name: Name for the container.
            smtp_port: Host port to map to SMTP (container port 1025).
            web_port: Host port to map to web UI (container port 8025).
            image: Docker image to use.
        """
        self.container_name = container_name
        self.smtp_port = smtp_port
        self.web_port = web_port
        self.image = image
        self._runtime_type = self._detect_runtime()
        self._runtime = self._runtime_type.value if self._runtime_type != RuntimeType.NONE else None

    @staticmethod
    def _detect_runtime() -> RuntimeType:
        """Detect which container runtime is available.

        Returns:
            RuntimeType: DOCKER, PODMAN, or NONE.
        """
        # Check for Docker first
        if shutil.which("docker"):
            try:
                result = subprocess.run(
                    ["docker", "--version"],
                    capture_output=True,
                    timeout=5,
                    check=False,
                )
                if result.returncode == 0:
                    return RuntimeType.DOCKER
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

        # Check for Podman
        if shutil.which("podman"):
            try:
                result = subprocess.run(
                    ["podman", "--version"],
                    capture_output=True,
                    timeout=5,
                    check=False,
                )
                if result.returncode == 0:
                    return RuntimeType.PODMAN
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

        return RuntimeType.NONE

    @property
    def is_available(self) -> bool:
        """Check if a container runtime is available.

        Returns:
            True if Docker or Podman is available.
        """
        return self._runtime_type != RuntimeType.NONE

    @property
    def smtp_host(self) -> str:
        """Get the SMTP host address.

        Returns:
            The host address for SMTP connections (usually "localhost").
        """
        return "localhost"

    @property
    def web_url(self) -> str:
        """Get the web UI URL.

        Returns:
            URL for the Mailpit web interface.
        """
        return f"http://localhost:{self.web_port}"

    @property
    def api_url(self) -> str:
        """Get the API base URL.

        Returns:
            URL for the Mailpit REST API.
        """
        return f"http://localhost:{self.web_port}/api"

    def _run_command(
        self,
        args: list[str],
        check: bool = True,
        timeout: int | None = 30,
    ) -> tuple[int, str, str]:
        """Run a container runtime command.

        Args:
            args: Command arguments.
            check: Whether to raise on non-zero exit.
            timeout: Command timeout in seconds.

        Returns:
            Tuple of (return_code, stdout, stderr).

        Raises:
            NoRuntimeAvailableError: If no runtime is available.
        """
        if not self.is_available:
            msg = (
                "No container runtime available. Please install Docker or Podman.\n"
                "Docker: https://docs.docker.com/get-docker/\n"
                "Podman: https://podman.io/getting-started/installation"
            )
            raise NoRuntimeAvailableError(msg)

        full_cmd = [self._runtime, *args]  # type: ignore[list-item]
        result = subprocess.run(
            full_cmd,  # type: ignore[arg-type]
            capture_output=True,
            timeout=timeout,
            check=check,
            text=True,
        )
        return result.returncode, result.stdout, result.stderr

    def is_running(self) -> bool:
        """Check if the Mailpit container is running.

        Returns:
            True if the container is running.
        """
        if not self.is_available:
            return False

        try:
            _, stdout, _ = self._run_command(
                [
                    "ps",
                    "--filter",
                    f"name=^{self.container_name}$",
                    "--format",
                    "{{.Names}}",
                ],
                check=False,
            )
            return self.container_name in stdout.strip()
        except (subprocess.CalledProcessError, NoRuntimeAvailableError):
            return False

    def exists(self) -> bool:
        """Check if the container exists (running or stopped).

        Returns:
            True if the container exists.
        """
        if not self.is_available:
            return False

        try:
            _, stdout, _ = self._run_command(
                [
                    "ps",
                    "-a",
                    "--filter",
                    f"name=^{self.container_name}$",
                    "--format",
                    "{{.Names}}",
                ],
                check=False,
            )
            return self.container_name in stdout.strip()
        except (subprocess.CalledProcessError, NoRuntimeAvailableError):
            return False

    def start(self, wait: bool = True, timeout: int = 30) -> bool:
        """Start the Mailpit container.

        Args:
            wait: Whether to wait for the container to be ready.
            timeout: Maximum seconds to wait for container to start.

        Returns:
            True if the container was started successfully.

        Raises:
            NoRuntimeAvailableError: If no runtime is available.
        """
        # If already running, return early
        if self.is_running():
            return True

        # Remove existing stopped container
        if self.exists():
            self._run_command(["rm", "-f", self.container_name], check=False)

        # Start new container
        self._run_command([
            "run",
            "-d",
            "--name",
            self.container_name,
            "-p",
            f"{self.smtp_port}:1025",
            "-p",
            f"{self.web_port}:8025",
            self.image,
        ])

        if wait:
            return self._wait_for_ready(timeout)
        return True

    def _wait_for_ready(self, timeout: int = 30) -> bool:
        """Wait for Mailpit to be ready to accept connections.

        Args:
            timeout: Maximum seconds to wait.

        Returns:
            True if Mailpit is ready, False if timeout reached.
        """
        import socket

        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                # Try to connect to the SMTP port
                with socket.create_connection(
                    (self.smtp_host, self.smtp_port),
                    timeout=1,
                ):
                    return True
            except (OSError, TimeoutError):
                time.sleep(0.5)
        return False

    def stop(self, remove: bool = True) -> None:
        """Stop the Mailpit container.

        Args:
            remove: Whether to remove the container after stopping.
        """
        if not self.is_available:
            return

        try:
            self._run_command(["stop", self.container_name], check=False, timeout=10)
            if remove:
                self._run_command(["rm", self.container_name], check=False)
        except (subprocess.TimeoutExpired, NoRuntimeAvailableError):
            pass

    def clear_messages(self) -> bool:
        """Clear all messages from Mailpit.

        This uses the Mailpit REST API to delete all messages.

        Returns:
            True if messages were cleared successfully.
        """
        import urllib.request

        try:
            req = urllib.request.Request(
                f"{self.api_url}/v1/messages",
                method="DELETE",
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                return response.status == 200
        except Exception:
            return False

    def get_messages(self) -> list[dict[str, object]]:
        """Get all messages from Mailpit.

        Returns:
            List of message dictionaries from the Mailpit API.
        """
        import json
        import urllib.request

        try:
            req = urllib.request.Request(f"{self.api_url}/v1/messages")
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode())
                return data.get("messages", [])  # type: ignore[no-any-return]
        except Exception:
            return []

    def __enter__(self) -> Self:
        """Enter context manager - start the container.

        Returns:
            The container instance.
        """
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Exit context manager - stop the container."""
        self.stop()
