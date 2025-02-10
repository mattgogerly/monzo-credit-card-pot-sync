import pytest

from app.domain.auth_providers import (
    AmericanExpressAuthProvider,
    AuthProviderType,
    MonzoAuthProvider,
    provider_mapping,
)
from app.errors import AuthException


def test_monzo_provider_initialization(monzo_provider):
    assert monzo_provider.name == "Monzo"
    assert monzo_provider.type == AuthProviderType.MONZO.value
    assert monzo_provider.icon_name == "monzo.svg"
    assert monzo_provider.api_url == "https://api.monzo.com"
    assert monzo_provider.auth_url == "https://auth.monzo.com"
    assert monzo_provider.token_url == "https://api.monzo.com"
    assert monzo_provider.token_endpoint == "/oauth2/token"
    assert monzo_provider.callback_url == "http://localhost:1337/auth/callback/monzo"
    assert monzo_provider.setting_prefix == "monzo"


def test_amex_provider_initialization(amex_provider):
    assert amex_provider.name == "American Express"
    assert amex_provider.type == AuthProviderType.AMEX.value
    assert amex_provider.icon_name == "amex.svg"
    assert amex_provider.api_url == "https://api.truelayer.com"
    assert amex_provider.auth_url == "https://auth.truelayer.com"
    assert amex_provider.token_url == "https://auth.truelayer.com"
    assert amex_provider.token_endpoint == "/connect/token"
    assert amex_provider.callback_url == "http://localhost:1337/auth/callback/truelayer"
    assert amex_provider.setting_prefix == "truelayer"


def test_get_default_oauth_request_params(setting_repository, monzo_provider):
    params = monzo_provider.get_default_oauth_request_params()
    assert params["client_id"] == "setting_value"
    assert params["response_type"] == "code"
    assert params["redirect_uri"] == monzo_provider.callback_url
    assert "state" in params


def test_create_oauth_request_url(setting_repository, monzo_provider):
    url = monzo_provider.create_oauth_request_url()
    assert url.startswith(monzo_provider.auth_url)
    assert "client_id=setting_value" in url
    assert "response_type=code" in url
    assert "redirect_uri=http%3A%2F%2Flocalhost%3A1337%2Fauth%2Fcallback%2Fmonzo" in url
    assert "response_mode=form_post" in url


def test_get_oauth_token_request_body(setting_repository, monzo_provider):
    body = monzo_provider.get_oauth_token_request_body("test_code")
    assert body["client_id"] == "setting_value"
    assert body["client_secret"] == "setting_value"
    assert body["code"] == "test_code"
    assert body["grant_type"] == "authorization_code"
    assert body["redirect_uri"] == monzo_provider.callback_url


def test_handle_oauth_code_callback(setting_repository, requests_mock, monzo_provider):
    response = {
        "access_token": "test_access_token",
        "refresh_token": "test_refresh_token",
        "expires_in": 3600,
    }
    requests_mock.post(monzo_provider.get_token_url(), status_code=200, json=response)
    tokens = monzo_provider.handle_oauth_code_callback("code")
    assert tokens["access_token"] == "test_access_token"
    assert tokens["refresh_token"] == "test_refresh_token"
    assert tokens["expires_in"] == 3600


def test_handle_oauth_code_callback_error(setting_repository, requests_mock, monzo_provider):
    requests_mock.post(monzo_provider.get_token_url(), status_code=500)
    with pytest.raises(AuthException, match="No access token returned"):
        monzo_provider.refresh_access_token("test_refresh_token")


def test_get_refresh_request_body(setting_repository, monzo_provider):
    body = monzo_provider.get_refresh_request_body("test_refresh_token")
    assert body["client_id"] == "setting_value"
    assert body["client_secret"] == "setting_value"
    assert body["grant_type"] == "refresh_token"
    assert body["refresh_token"] == "test_refresh_token"


def test_refresh_access_token(setting_repository, requests_mock, monzo_provider):
    response = {
        "access_token": "test_access_token",
        "refresh_token": "test_refresh_token",
        "expires_in": 3600,
    }
    requests_mock.post(monzo_provider.get_token_url(), status_code=200, json=response)
    tokens = monzo_provider.refresh_access_token("test_refresh_token")
    assert tokens["access_token"] == "test_access_token"
    assert tokens["refresh_token"] == "test_refresh_token"
    assert tokens["expires_in"] == 3600


def test_refresh_access_token_error(setting_repository, requests_mock, monzo_provider):
    requests_mock.post(monzo_provider.get_token_url(), status_code=500)
    with pytest.raises(AuthException, match="No access token returned"):
        monzo_provider.refresh_access_token("test_refresh_token")


def test_get_monzo_provider_specific_oauth_request_params(monzo_provider):
    params = monzo_provider.get_provider_specific_oauth_request_params()
    assert params == {"response_mode": "form_post"}


def test_get_american_express_provider_specific_oauth_request_params(amex_provider):
    params = amex_provider.get_provider_specific_oauth_request_params()
    assert params == {"providers": "uk-ob-amex", "scope": amex_provider.oauth_scopes}


def test_provider_mapping():
    assert isinstance(provider_mapping[AuthProviderType.MONZO], MonzoAuthProvider)
    assert isinstance(provider_mapping[AuthProviderType.AMEX], AmericanExpressAuthProvider)