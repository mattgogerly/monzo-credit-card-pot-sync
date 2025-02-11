from time import time
from urllib import parse
from app.domain.accounts import MonzoAccount, TrueLayerAccount

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

    requests_mock.put("https://api.monzo.com/pots/1/deposit", status_code=200)

    account = MonzoAccount("access_token", "refresh_token", int(time()) + 1000)
    account.add_to_pot("1", 500)


def test_monzo_account_withdraw_from_pot(requests_mock):
    account_response = {"accounts": [{"id": "id", "type": "uk_retail", "currency": "GBP"}]}
    requests_mock.get("https://api.monzo.com/accounts", status_code=200, json=account_response)

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
    assert pending_amount == 150

def test_truelayer_account_get_total_balance(requests_mock):
    cards_response = {
        "results": [
            {"account_id": "1", "provider": {"display_name": "AMEX"}},  # AMEX Card (should include pending)
            {"account_id": "2", "provider": {"display_name": "VISA"}}  # Non-AMEX (should NOT include pending)
        ]
    }
    requests_mock.get("https://api.truelayer.com/data/v1/cards", status_code=200, json=cards_response)

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

    account = TrueLayerAccount("American Express", "access_token", "refresh_token", time() + 1000)

    # Only AMEX card includes pending transactions
    # Card 1 (AMEX): 500 (balance) + 150 (pending) = 650
    # Card 2 (VISA): 750 (balance) (pending ignored) = 750
    # Total balance = 650 + 750 = 1400
    assert account.get_total_balance() == 140000  # Total in pence (multiplied by 100)
