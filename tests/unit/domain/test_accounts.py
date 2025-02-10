from time import time

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
    response = {"accounts": [{"id": "id"}]}
    requests_mock.get("https://api.monzo.com/accounts", status_code=200, json=response)
    account = MonzoAccount("access_token", "refresh_token", time() + 1000)
    assert account.get_account_id() == "id"

def test_monzo_account_get_pots_joint_account(requests_mock):
    # When a joint account id is provided, the query should include it.
    account_response = {"accounts": [{"id": "joint_123"}]}
    requests_mock.get("https://api.monzo.com/accounts", status_code=200, json=account_response)

    pot_response = {"pots": [{"id": "1", "deleted": False}]}
    requests_mock.get("https://api.monzo.com/pots?current_account_id=joint_123", status_code=200, json=pot_response)

    account = MonzoAccount("access_token", "refresh_token", 1000, "pot", account_id="joint_123")
    pots = account.get_pots()
    assert len(pots) == 1

def test_monzo_account_get_pots(requests_mock):
    account_response = {"accounts": [{"id": "id"}]}
    requests_mock.get("https://api.monzo.com/accounts", status_code=200, json=account_response)

    pot_response = {"pots": [{"id": "1", "deleted": False}, {"id": "2", "deleted": True}]}
    requests_mock.get("https://api.monzo.com/pots?current_account_id=id", status_code=200, json=pot_response)

    account = MonzoAccount("access_token", "refresh_token", time() + 1000)
    pots = account.get_pots()
    # Only non-deleted pots should be returned.
    assert len(pots) == 1

def test_monzo_account_get_pot_balance(requests_mock):
    account_response = {"accounts": [{"id": "id"}]}
    requests_mock.get("https://api.monzo.com/accounts", status_code=200, json=account_response)

    pot_response = {
        "pots": [
            {"id": "1", "deleted": False, "balance": 500},
            {"id": "2", "deleted": True},
        ]
    }
    requests_mock.get("https://api.monzo.com/pots?current_account_id=id", status_code=200, json=pot_response)

    account = MonzoAccount("access_token", "refresh_token", time() + 1000)
    assert account.get_pot_balance("1") == 500

def test_monzo_account_add_to_pot(requests_mock):
    account_response = {"accounts": [{"id": "id"}]}
    requests_mock.get("https://api.monzo.com/accounts", status_code=200, json=account_response)

    requests_mock.put("https://api.monzo.com/pots/1/deposit", status_code=200)

    account = MonzoAccount("access_token", "refresh_token", time() + 1000)
    account.add_to_pot("1", 500)

def test_monzo_account_withdraw_from_pot(requests_mock):
    account_response = {"accounts": [{"id": "id"}]}
    requests_mock.get("https://api.monzo.com/accounts", status_code=200, json=account_response)

    requests_mock.put("https://api.monzo.com/pots/1/withdraw", status_code=200)

    account = MonzoAccount("access_token", "refresh_token", time() + 1000)
    account.withdraw_from_pot("1", 500)

def test_monzo_account_send_notification(requests_mock):
    account_response = {"accounts": [{"id": "id"}]}
    requests_mock.get("https://api.monzo.com/accounts", status_code=200, json=account_response)

    requests_mock.post("https://api.monzo.com/feed", status_code=200)

    account = MonzoAccount("access_token", "refresh_token", time() + 1000)
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

def test_truelayer_account_get_total_balance(requests_mock):
    cards_response = {"results": [{"account_id": "1"}, {"account_id": "2"}]}
    requests_mock.get("https://api.truelayer.com/data/v1/cards", status_code=200, json=cards_response)

    balance_response_one = {"results": [{"account_id": "1", "current": 500}]}
    requests_mock.get("https://api.truelayer.com/data/v1/cards/1/balance", status_code=200, json=balance_response_one)

    balance_response_two = {"results": [{"account_id": "2", "current": 750}]}
    requests_mock.get("https://api.truelayer.com/data/v1/cards/2/balance", status_code=200, json=balance_response_two)

    account = TrueLayerAccount("American Express", "access_token", "refresh_token", time() + 1000)
    # Total balance is 500 + 750 = 1250 pounds,
    # multiplied by 100 to convert into pence.
    assert account.get_total_balance() == 125000