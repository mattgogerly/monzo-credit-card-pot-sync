import pytest

from app.domain.auth_providers import (
    MonzoAuthProvider,
    AmericanExpressAuthProvider,
)
from app.models.setting_repository import SqlAlchemySettingRepository


class MockDatabase:
    def __init__(self):
        self.session = None


@pytest.fixture
def monzo_provider():
    return MonzoAuthProvider()


@pytest.fixture
def amex_provider():
    return AmericanExpressAuthProvider()


@pytest.fixture
def setting_repository(mocker):
    setting_repository = SqlAlchemySettingRepository(MockDatabase())
    mocker.patch.object(setting_repository, "get", return_value="setting_value")

    mocker.patch("app.domain.auth_providers.repository", setting_repository)
