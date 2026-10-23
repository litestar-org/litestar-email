from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from litestar import Litestar

    from litestar_email import EmailConfig, EmailPlugin

pytestmark = pytest.mark.anyio


def test_plugin_instantiation_with_defaults() -> None:
    """Test that the plugin can be instantiated with default configuration."""
    from litestar_email import EmailPlugin

    plugin = EmailPlugin()
    assert plugin.config.backend == "console"
    assert plugin.config.from_email == "noreply@localhost"
    assert plugin.config.from_name == ""
    assert plugin.config.fail_silently is False


def test_plugin_instantiation_with_config(email_config: "EmailConfig") -> None:
    """Test that the plugin can be instantiated with custom configuration."""
    from litestar_email import EmailPlugin

    plugin = EmailPlugin(config=email_config)
    assert plugin.config.backend == "memory"
    assert plugin.config.from_email == "test@example.com"
    assert plugin.config.from_name == "Test Sender"


def test_config_defaults() -> None:
    """Test that the configuration has sensible defaults."""
    from litestar_email import EmailConfig

    config = EmailConfig()
    assert config.backend == "console"
    assert config.from_email == "noreply@localhost"
    assert config.from_name == ""
    assert config.fail_silently is False
    assert config.email_service_dependency_key == "mailer"
    assert config.email_service_state_key == "mailer"


def test_plugin_with_litestar_app(app: "Litestar", email_plugin: "EmailPlugin") -> None:
    """Test that the plugin integrates with a Litestar application."""
    assert email_plugin in app.plugins
    assert email_plugin.config.backend == "memory"


def test_plugin_registers_dependencies_and_state() -> None:
    """Test that the plugin registers dependencies, state, and signature namespace."""
    from litestar.config.app import AppConfig

    from litestar_email import EmailConfig, EmailPlugin, EmailService

    config = EmailConfig()
    plugin = EmailPlugin(config=config)
    app_config = AppConfig()

    plugin.on_app_init(app_config)

    assert config.email_service_dependency_key in app_config.dependencies
    assert config.email_service_state_key in app_config.state
    assert app_config.state[config.email_service_state_key] is config
    assert "EmailService" in app_config.signature_namespace
    assert isinstance(plugin.get_service(app_config.state), EmailService)


def test_plugin_injects_email_service_into_handler() -> None:
    """Test that a handler receives an EmailService (not the context-manager provider)."""
    from litestar import Litestar, get
    from litestar.testing import TestClient

    from litestar_email import EmailConfig, EmailPlugin, EmailService

    @get("/")
    async def handler(mailer: EmailService) -> str:
        return type(mailer).__name__

    app = Litestar(route_handlers=[handler], plugins=[EmailPlugin(config=EmailConfig())])
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert response.text == "EmailService"
