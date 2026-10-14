"""App log level follows ENVIRONMENT: DEBUG everywhere but production."""

import logging

import pytest

from app.core.config import Settings


@pytest.mark.parametrize(
    "environment", ["production", "prod", "Production", " production "]
)
def test_production_logs_at_info(environment):
    assert Settings(environment=environment).app_log_level == logging.INFO


@pytest.mark.parametrize("environment", ["local", "preprod", "test", ""])
def test_other_environments_log_at_debug(environment):
    assert Settings(environment=environment).app_log_level == logging.DEBUG


def test_main_applies_level_to_app_loggers_only():
    from app.core.config import settings
    from app import main  # noqa: F401 — importing configures logging

    assert (
        logging.getLogger("app.services.guest_messages").getEffectiveLevel()
        == settings.app_log_level
    )
    assert logging.getLogger("pymongo").getEffectiveLevel() > logging.DEBUG
