import pytest
from time import time
from urllib import parse
from flask import Flask
from app.extensions import db
from app.domain.accounts import MonzoAccount, TrueLayerAccount

app = Flask(__name__)
# Adjust test configuration so that URL building and SQLAlchemy work properly.
app.config.update({
    "TESTING": True,
    "SERVER_NAME": "localhost",  # Required for url_for when outside a request
    "SQLALCHEMY_DATABASE_URI": "sqlite://",  # In-memory database for testing
    "SECRET_KEY": "testing",
})
db.init_app(app)

def test_new_monzo_account():
    account = MonzoAccount("access_token", "refresh_token", 1000, "pot")
    assert account.type == "Monzo"
    assert account.access_token == "access_token"
    assert account.refresh_token == "refresh_token"
    assert account.token_expiry == 1000
    assert account.pot_id == "pot"

def test_new_truelayer_account():
    account = TrueLayerAccount("American Express", "access_token", "refresh_token", 1000, "pot")
    assert account.type == "American Express"
    assert account.access_token == "access_token"
    assert account.refresh_token == "refresh_token"
    assert account.token_expiry == 1000
    assert account.pot_id == "pot"

def test_is_token_within_expiry_window_true():
    account = TrueLayerAccount("American Express", "access_token", "refresh_token", time() + 1)
    assert account.is_token_within_expiry_window()

def test_is_token_within_expiry_window_false():
    account = TrueLayerAccount("American Express", "access_token", "refresh_token", time() + 1000)
    assert not account.is_token_within_expiry_window()

def test_get_auth_header():
    account = MonzoAccount("access_token", "refresh_token", time() + 1000)
    assert account.get_auth_header() == {"Authorization": "Bearer access_token"}

def test_monzo_account_ping(requests_mock):
    requests_mock.get("https://api.monzo.com/ping/whoami", status_code=200)
    account = MonzoAccount("access_token", "refresh_token", time() + 1000)
    account.ping()

def test_monzo_account_ping_error(requests_mock):
    requests_mock.get("https://api.monzo.com/ping/whoami", status_code=401)
    account = MonzoAccount("access_token", "refresh_token", time() + 1000)
    account.ping()

def test_monzo_account_get_account_id(requests_mock):
    response = {"accounts": [{"id": "id", "type": "uk_retail", "currency": "GBP"}]}
    requests_mock.get("https://api.monzo.com/accounts", status_code=200, json=response)
    account = MonzoAccount("access_token", "refresh_token", int(time()) + 1000)
    assert account.get_account_id() == "id"


def test_monzo_account_get_pots_joint_account(requests_mock):
    # When testing for joint accounts, update mocked response to include the joint type.
    account_response = {"accounts": [{"id": "joint_123", "type": "uk_retail_joint", "currency": "GBP"}]}
    requests_mock.get("https://api.monzo.com/accounts", status_code=200, json=account_response)

    pot_response = {"pots": [{"id": "1", "deleted": False}]}
    req_url = f"https://api.monzo.com/pots?{parse.urlencode({'current_account_id': 'joint_123'})}"
    requests_mock.get(req_url, status_code=200, json=pot_response)

    account = MonzoAccount("access_token", "refresh_token", int(time()) + 1000, "pot", account_id="joint_123")
    pots = account.get_pots("joint")
    assert pots == [{"id": "1", "deleted": False}]


def test_monzo_account_get_pots(requests_mock):
    account_response = {"accounts": [{"id": "id", "type": "uk_retail", "currency": "GBP"}]}
    requests_mock.get("https://api.monzo.com/accounts", status_code=200, json=account_response)

    pot_response = {"pots": [{"id": "1", "deleted": False}, {"id": "2", "deleted": True}]}
    req_url = f"https://api.monzo.com/pots?{parse.urlencode({'current_account_id': 'id'})}"
    requests_mock.get(req_url, status_code=200, json=pot_response)

    account = MonzoAccount("access_token", "refresh_token", int(time()) + 1000)
    pots = account.get_pots()
    # Only non-deleted pots should be returned.
    assert pots == [{"id": "1", "deleted": False}]


def test_monzo_account_get_pot_balance(requests_mock):
    account_response = {"accounts": [{"id": "id", "type": "uk_retail", "currency": "GBP"}]}
    requests_mock.get("https://api.monzo.com/accounts", status_code=200, json=account_response)

    pot_response = {
        "pots": [
            {"id": "1", "deleted": False, "balance": 500},
            {"id": "2", "deleted": True},
        ]
    }
    req_url = f"https://api.monzo.com/pots?{parse.urlencode({'current_account_id': 'id'})}"
    requests_mock.get(req_url, status_code=200, json=pot_response)

    account = MonzoAccount("access_token", "refresh_token", int(time()) + 1000)
    assert account.get_pot_balance("1") == 500


def test_monzo_account_add_to_pot(requests_mock):
    account_response = {"accounts": [{"id": "id", "type": "uk_retail", "currency": "GBP"}]}
    requests_mock.get("https://api.monzo.com/accounts", status_code=200, json=account_response)
    # Add a mock for the pots endpoint required by add_to_pot (GET pots?current_account_id=id)
    pots_url = f"https://api.monzo.com/pots?{parse.urlencode({'current_account_id': 'id'})}"
    pot_response = {"pots": [{"id": "1", "deleted": False, "balance": 0}]}
    requests_mock.get(pots_url, status_code=200, json=pot_response)

    requests_mock.put("https://api.monzo.com/pots/1/deposit", status_code=200)

    account = MonzoAccount("access_token", "refresh_token", int(time()) + 1000)
    account.add_to_pot("1", 500)


def test_monzo_account_withdraw_from_pot(requests_mock):
    account_response = {"accounts": [{"id": "id", "type": "uk_retail", "currency": "GBP"}]}
    requests_mock.get("https://api.monzo.com/accounts", status_code=200, json=account_response)
    # Add a mock for the pots endpoint required by withdraw_from_pot (GET pots?current_account_id=id)
    pots_url = f"https://api.monzo.com/pots?{parse.urlencode({'current_account_id': 'id'})}"
    pot_response = {"pots": [{"id": "1", "deleted": False, "balance": 1000}]}
    requests_mock.get(pots_url, status_code=200, json=pot_response)
    requests_mock.put("https://api.monzo.com/pots/1/withdraw", status_code=200)

    account = MonzoAccount("access_token", "refresh_token", int(time()) + 1000)
    account.withdraw_from_pot("1", 500)


def test_monzo_account_send_notification(requests_mock):
    account_response = {"accounts": [{"id": "id", "type": "uk_retail", "currency": "GBP"}]}
    requests_mock.get("https://api.monzo.com/accounts", status_code=200, json=account_response)

    requests_mock.post("https://api.monzo.com/feed", status_code=200)

    account = MonzoAccount("access_token", "refresh_token", int(time()) + 1000)
    account.send_notification("title", "message")

def test_truelayer_account_ping(requests_mock):
    requests_mock.get("https://api.truelayer.com/data/v1/me", status_code=200)
    account = TrueLayerAccount("American Express", "access_token", "refresh_token", time() + 1000)
    account.ping()

def test_truelayer_account_ping_error(requests_mock):
    requests_mock.get("https://api.truelayer.com/data/v1/me", status_code=401)
    account = TrueLayerAccount("American Express", "access_token", "refresh_token", time() + 1000)
    account.ping()

def test_truelayer_account_get_cards(requests_mock):
    response = {"results": [{"account_id": "id"}]}
    requests_mock.get("https://api.truelayer.com/data/v1/cards", status_code=200, json=response)

    account = TrueLayerAccount("American Express", "access_token", "refresh_token", time() + 1000)
    cards = account.get_cards()
    assert len(cards) == 1

def test_truelayer_account_get_card_balance(requests_mock):
    response = {"results": [{"account_id": "id", "current": 500}]}
    requests_mock.get("https://api.truelayer.com/data/v1/cards/1/balance", status_code=200, json=response)

    account = TrueLayerAccount("American Express", "access_token", "refresh_token", time() + 1000)
    assert account.get_card_balance("1") == 500

def test_truelayer_account_get_pending_transactions(requests_mock):
    response = {"results": [{"amount": 100}, {"amount": 50}]}
    requests_mock.get("https://api.truelayer.com/data/v1/cards/1/transactions/pending", status_code=200, json=response)

    account = TrueLayerAccount("American Express", "access_token", "refresh_token", time() + 1000)
    pending_amount = account.get_pending_transactions("1")
    assert pending_amount == [100, 50]

def test_truelayer_account_get_total_balance(requests_mock):
    # Mock the response for cards (AMEX and VISA)
    cards_response = {
        "results": [
            {"account_id": "1", "provider": {"display_name": "AMEX"}},  # AMEX Card (should include pending)
            {"account_id": "2", "provider": {"display_name": "VISA"}}  # Non-AMEX (should NOT include pending)
        ]
    }
    requests_mock.get("https://api.truelayer.com/data/v1/cards", status_code=200, json=cards_response)
    
    # Mock the response for balances
    balance_response_one = {"results": [{"account_id": "1", "current": 500}]}
    requests_mock.get("https://api.truelayer.com/data/v1/cards/1/balance", status_code=200, json=balance_response_one)
    
    balance_response_two = {"results": [{"account_id": "2", "current": 750}]}
    requests_mock.get("https://api.truelayer.com/data/v1/cards/2/balance", status_code=200, json=balance_response_two)
    
    # Mock pending transactions (ONLY for AMEX card)
    pending_response_one = {"results": [{"amount": 100}, {"amount": 50}]}  # AMEX should include these
    requests_mock.get("https://api.truelayer.com/data/v1/cards/1/transactions/pending", status_code=200, json=pending_response_one)
    
    # Non-AMEX card (should be ignored)
    pending_response_two = {"results": [{"amount": 200}, {"amount": 100}]}
    requests_mock.get("https://api.truelayer.com/data/v1/cards/2/transactions/pending", status_code=200, json=pending_response_two)
    
    # Create an instance of TrueLayerAccount
    account = TrueLayerAccount("American Express", "access_token", "refresh_token", time() + 1000)

    # Total balance calculation:
    # AMEX card: 500 (balance) + 150 (pending) = 650
    # VISA card: 750 (balance) (pending ignored) = 750
    # Total balance = 650 + 750 = 1400 (in pence, so 1400 * 100 = 140000)
    
    # Assert that the total balance is calculated correctly
    assert account.get_total_balance() == 140000  # Total in pence (multiplied by 100)

def test_monzo_account_refresh_access_token_success(monkeypatch, requests_mock):
    """
    Simulate successful token refresh with the MonzoAuthProvider.
    """
    from app.domain.accounts import MonzoAccount
    requests_mock.post("https://api.monzo.com/oauth2/token", json={
        "access_token": "new_access",
        "refresh_token": "new_refresh",
        "expires_in": 3600
    })
    account = MonzoAccount("old_access", "old_refresh", 100, "test_pot")
    monkeypatch.setattr(account.auth_provider, "get_token_url", lambda: "https://api.monzo.com/oauth2/token")
    with app.app_context():
        db.create_all()
        account.refresh_access_token()
        db.drop_all()  # cleanup
    assert account.access_token == "new_access"
    assert account.refresh_token == "new_refresh"

def test_monzo_account_refresh_access_token_keyerror(monkeypatch, requests_mock):
    """
    Exercise the KeyError branch, ensuring an exception is raised when fields are missing.
    """
    from app.domain.accounts import MonzoAccount
    requests_mock.post("https://api.monzo.com/oauth2/token", json={})
    account = MonzoAccount("old_access", "old_refresh", 100, "test_pot")
    monkeypatch.setattr(account.auth_provider, "get_token_url", lambda: "https://api.monzo.com/oauth2/token")
    with app.app_context():
        db.create_all()
        with pytest.raises(Exception) as excinfo:  # or pytest.raises(AuthException) if AuthException is expected
            account.refresh_access_token()
        db.drop_all()
    assert "missing required fields" in str(excinfo.value)

def test_monzo_account_refresh_access_token_authexception(monkeypatch, requests_mock):
    """
    Exercise the AuthException branch, ensuring it’s raised when underlying logic signals an auth failure.
    """
    from app.domain.accounts import MonzoAccount
    from app.errors import AuthException
    requests_mock.post("https://api.monzo.com/oauth2/token", json={"error": "invalid_grant"}, status_code=400)
    account = MonzoAccount("old_access", "old_refresh", 100, "test_pot")
    monkeypatch.setattr(account.auth_provider, "get_token_url", lambda: "https://api.monzo.com/oauth2/token")
    with app.app_context():
        db.create_all()
        with pytest.raises(AuthException):
            account.refresh_access_token()
        db.drop_all()