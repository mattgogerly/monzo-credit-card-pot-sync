import os
from time import time

import pytest

from app import create_app
from app.domain.accounts import MonzoAccount, TrueLayerAccount
from app.domain.auth_providers import (
    AmericanExpressAuthProvider,
    AuthProviderType,
    BarclaycardAuthProvider,
    MonzoAuthProvider,
)
from app.domain.settings import Setting
from app.extensions import db
from app.models.account_repository import SqlAlchemyAccountRepository
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


@pytest.fixture(scope="function")
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


@pytest.fixture(scope="function")
def seed_data():
    monzo_account = MonzoAccount("access_token", "refresh_token", time() + 10000)
    amex_account = TrueLayerAccount(
        AuthProviderType.AMEX.value,
        "access_token",
        "refresh_token",
        time() + 10000,
        "pot_id",
    )

    account_repository = SqlAlchemyAccountRepository(db)
    account_repository.save(monzo_account)
    account_repository.save(amex_account)

    setting_repository = SqlAlchemySettingRepository(db)
    setting_repository.save(Setting("monzo_client_id", "monzo_dummy_client_id"))
    setting_repository.save(Setting("monzo_client_secret", "monzo_dummy_client_secret"))
    setting_repository.save(
        Setting("truelayer_client_id", os.getenv("TRUELAYER_SANDBOX_CLIENT_ID"))
    )
    setting_repository.save(
        Setting("truelayer_client_secret", os.getenv("TRUELAYER_SANDBOX_CLIENT_SECRET"))
    )


@pytest.fixture()
def barclaycard_sandbox_provider(mocker):
    barclaycard_provider = BarclaycardAuthProvider()
    barclaycard_provider.api_url = "https://api.truelayer-sandbox.com"
    barclaycard_provider.auth_url = "https://auth.truelayer-sandbox.com"
    barclaycard_provider.token_url = "https://auth.truelayer-sandbox.com"
    mocker.patch.object(
        barclaycard_provider,
        "get_provider_specific_oauth_request_params",
        return_value={
            "providers": "uk-cs-mock",
            "scope": barclaycard_provider.oauth_scopes,
        },
    )

    replaced_provider_mapping = {AuthProviderType.BARCLAYCARD: barclaycard_provider}
    mocker.patch("app.web.auth.provider_mapping", replaced_provider_mapping)
