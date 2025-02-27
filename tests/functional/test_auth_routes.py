import pytest
from urllib.parse import urlparse

def test_monzo_oauth_callback(test_client, requests_mock):
    requests_mock.post(
        "https://api.monzo.com/oauth2/token",
        json={"access_token": "access", "refresh_token": "refresh", "expires_in": 1000},
    )
    response = test_client.get("/auth/callback/monzo?code=123&state=Monzo-123")
    assert response.status_code == 302
    assert urlparse(response.location).path == "/accounts/"

def test_truelayer_oauth_callback(test_client, requests_mock):
    requests_mock.post(
        "https://auth.truelayer.com/connect/token",
        json={"access_token": "access", "refresh_token": "refresh", "expires_in": 1000},
    )
    response = test_client.get("/auth/callback/truelayer?code=123&state=Barclaycard-123")
    assert response.status_code == 302
    assert urlparse(response.location).path == "/accounts/"

def test_monzo_oauth_callback_missing_token(test_client, requests_mock):
    # Simulate token endpoint returning an error (missing required fields)
    requests_mock.post(
        "https://api.monzo.com/oauth2/token",
        json={"error": "invalid_request"},
        status_code=400
    )
    with pytest.raises(KeyError):
        test_client.get("/auth/callback/monzo?code=123&state=Monzo-123")

def test_truelayer_oauth_callback_missing_token(test_client, requests_mock):
    # Simulate token endpoint returning an empty response (missing access_token)
    requests_mock.post(
        "https://auth.truelayer.com/connect/token",
        json={},
        status_code=400
    )
    with pytest.raises(KeyError):
        test_client.get("/auth/callback/truelayer?code=123&state=Barclaycard-123")