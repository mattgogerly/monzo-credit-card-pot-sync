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
    account = TrueLayerAccount(
        "American Express", "access_token", "refresh_token", 1000, "pot"
    )
    assert account.type == "American Express"
    assert account.access_token == "access_token"
    assert account.refresh_token == "refresh_token"
    assert account.token_expiry == 1000
    assert account.pot_id == "pot"


def test_is_token_within_expiry_window_true():
    account = TrueLayerAccount(
        "American Express", "access_token", "refresh_token", time() + 1
    )
    assert account.is_token_within_expiry_window()


def test_is_token_within_expiry_window_false():
    account = TrueLayerAccount(
        "American Express", "access_token", "refresh_token", time() + 1000
    )
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
    response = {"accounts": [{"id": "id", "type": "uk_retail"}]}
    requests_mock.get("https://api.monzo.com/accounts", status_code=200, json=response)

    account = MonzoAccount("access_token", "refresh_token", time() + 1000)
    assert account.get_account_id() == "id"


def test_monzo_account_get_account_id_joint(requests_mock):
    response = {"accounts": [{"id": "id", "type": "uk_retail_joint"}]}
    requests_mock.get("https://api.monzo.com/accounts", status_code=200, json=response)

    account = MonzoAccount("access_token", "refresh_token", time() + 1000)
    assert account.get_account_id(account_type="uk_retail_joint") == "id"


def test_monzo_account_get_pots(requests_mock):
    account_response = {"accounts": [{"id": "id", "type": "uk_retail"}]}
    requests_mock.get(
        "https://api.monzo.com/accounts", status_code=200, json=account_response
    )

    pot_response = {
        "pots": [{"id": "1", "deleted": False}, {"id": "2", "deleted": True}]
    }
    requests_mock.get(
        "https://api.monzo.com/pots?current_account_id=id",
        status_code=200,
        json=pot_response,
    )

    account = MonzoAccount("access_token", "refresh_token", time() + 1000)
    assert len(account.get_pots()) == 1


def test_monzo_account_get_pot_balance(requests_mock):
    account_response = {"accounts": [{"id": "id", "type": "uk_retail"}]}
    requests_mock.get(
        "https://api.monzo.com/accounts", status_code=200, json=account_response
    )

    pot_response = {
        "pots": [
            {"id": "1", "deleted": False, "balance": 500},
            {"id": "2", "deleted": True},
        ]
    }
    requests_mock.get(
        "https://api.monzo.com/pots?current_account_id=id",
        status_code=200,
        json=pot_response,
    )

    account = MonzoAccount("access_token", "refresh_token", time() + 1000)
    assert account.get_pot_balance("1") == 500


def test_monzo_account_add_to_pot(requests_mock):
    account_response = {"accounts": [{"id": "id", "type": "uk_retail"}]}
    requests_mock.get(
        "https://api.monzo.com/accounts", status_code=200, json=account_response
    )

    requests_mock.put("https://api.monzo.com/pots/1/deposit", status_code=200)

    account = MonzoAccount("access_token", "refresh_token", time() + 1000)
    account.add_to_pot("1", 500)


def test_monzo_account_withdraw_from_pot(requests_mock):
    account_response = {"accounts": [{"id": "id", "type": "uk_retail"}]}
    requests_mock.get(
        "https://api.monzo.com/accounts", status_code=200, json=account_response
    )

    requests_mock.put("https://api.monzo.com/pots/1/withdraw", status_code=200)

    account = MonzoAccount("access_token", "refresh_token", time() + 1000)
    account.withdraw_from_pot("1", 500)


def test_monzo_account_send_notification(requests_mock):
    account_response = {"accounts": [{"id": "id", "type": "uk_retail"}]}
    requests_mock.get(
        "https://api.monzo.com/accounts", status_code=200, json=account_response
    )

    requests_mock.post("https://api.monzo.com/feed", status_code=200)

    account = MonzoAccount("access_token", "refresh_token", time() + 1000)
    account.send_notification("title", "message")


def test_truelayer_account_ping(requests_mock):
    requests_mock.get("https://api.truelayer.com/data/v1/me", status_code=200)
    account = TrueLayerAccount(
        "American Express", "access_token", "refresh_token", time() + 1000
    )
    account.ping()


def test_truelayer_account_ping_error(requests_mock):
    requests_mock.get("https://api.truelayer.com/data/v1/me", status_code=401)
    account = TrueLayerAccount(
        "American Express", "access_token", "refresh_token", time() + 1000
    )
    account.ping()


def test_truelayer_account_get_cards(requests_mock):
    response = {"results": [{"account_id": "id"}]}
    requests_mock.get(
        "https://api.truelayer.com/data/v1/cards", status_code=200, json=response
    )

    account = TrueLayerAccount(
        "American Express", "access_token", "refresh_token", time() + 1000
    )
    assert len(account.get_cards()) == 1


def test_truelayer_account_get_card_balance(requests_mock):
    response = {"results": [{"account_id": "id", "current": 500}]}
    requests_mock.get(
        "https://api.truelayer.com/data/v1/cards/1/balance",
        status_code=200,
        json=response,
    )

    account = TrueLayerAccount(
        "American Express", "access_token", "refresh_token", time() + 1000
    )
    assert account.get_card_balance("1") == 500


def test_truelayer_account_get_total_balance(requests_mock):
    cards_response = {"results": [{"account_id": "1"}, {"account_id": "2"}]}
    requests_mock.get(
        "https://api.truelayer.com/data/v1/cards", status_code=200, json=cards_response
    )

    balance_response_one = {"results": [{"account_id": "1", "current": 500}]}
    requests_mock.get(
        "https://api.truelayer.com/data/v1/cards/1/balance",
        status_code=200,
        json=balance_response_one,
    )

    balance_response_two = {"results": [{"account_id": "2", "current": 750}]}
    requests_mock.get(
        "https://api.truelayer.com/data/v1/cards/2/balance",
        status_code=200,
        json=balance_response_two,
    )

    account = TrueLayerAccount(
        "American Express", "access_token", "refresh_token", time() + 1000
    )

    # total balance should be multiplied by 100 to convert to pence
    assert account.get_total_balance() == 125000
