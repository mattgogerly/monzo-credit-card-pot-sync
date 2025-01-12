import pytest

from app import create_app
from app.domain.auth_providers import (
    AmericanExpressAuthProvider,
    MonzoAuthProvider,
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


@pytest.fixture(scope="module")
def test_client():
    test_config = {
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite://",
        "SECRET_KEY": "testing",
    }
    flask_app = create_app(test_config)

    with flask_app.test_client() as testing_client:
        with flask_app.app_context():
            yield testing_client
