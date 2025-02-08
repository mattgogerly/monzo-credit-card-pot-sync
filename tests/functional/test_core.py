from app.core import sync_balance


def test_core_flow_successful_no_change_required(
    mocker, test_client, requests_mock, seed_data
):
    ### Given ###
    mocker.patch("app.core.scheduler")

    # Mock ping calls for seeded accounts
    requests_mock.get("https://api.monzo.com/ping/whoami")
    requests_mock.get("https://api.truelayer.com/data/v1/me")

    # Mock pot balance call, returning 1000p (£10)
    requests_mock.get(
        "https://api.monzo.com/pots",
        json={"pots": [{"id": "pot_id", "balance": 1000, "deleted": False}]},
    )

    # Mock credit account balance calls, returning £10
    requests_mock.get(
        "https://api.truelayer.com/data/v1/cards",
        json={"results": [{"account_id": "card_id"}]},
    )
    requests_mock.get(
        "https://api.truelayer.com/data/v1/cards/card_id/balance",
        json={"results": [{"current": 10}]},
    )

    # Mock Monzo account balance call
    requests_mock.get(
        "https://api.monzo.com/accounts", json={"accounts": [{"id": "acc_id", "type": "uk_retail"}]}
    )
    requests_mock.get(
        "https://api.monzo.com/balance?account_id=acc_id", json={"balance": 100}
    )

    ### When ###
    sync_balance()

    ### Then ###
    last_call = requests_mock.last_request.qs
    assert "amount" not in last_call


def test_core_flow_successful_deposit(mocker, test_client, requests_mock, seed_data):
    ### Given ###
    mocker.patch("app.core.scheduler")

    # Mock ping calls for seeded accounts
    requests_mock.get("https://api.monzo.com/ping/whoami")
    requests_mock.get("https://api.truelayer.com/data/v1/me")

    # Mock pot balance call, returning 1000p (£10)
    requests_mock.get(
        "https://api.monzo.com/pots",
        json={"pots": [{"id": "pot_id", "balance": 1000, "deleted": False}]},
    )

    # Mock credit account balance calls, returning £1000
    requests_mock.get(
        "https://api.truelayer.com/data/v1/cards",
        json={"results": [{"account_id": "card_id"}]},
    )
    requests_mock.get(
        "https://api.truelayer.com/data/v1/cards/card_id/balance",
        json={"results": [{"current": 1000}]},
    )

    # Mock Monzo account balance call, returning £1000
    requests_mock.get(
        "https://api.monzo.com/accounts", json={"accounts": [{"id": "acc_id", "type": "uk_retail"}]}
    )
    requests_mock.get(
        "https://api.monzo.com/balance?account_id=acc_id", json={"balance": 100000}
    )

    # Mock pot deposit call
    requests_mock.put("https://api.monzo.com/pots/pot_id/deposit")

    ### When ###
    sync_balance()

    ### Then ###
    last_call = requests_mock.last_request.text
    assert "source_account_id=acc_id" in last_call

    # Expect a pot deposit of £990
    assert "amount=99000" in last_call


def test_core_flow_successful_withdrawal(mocker, test_client, requests_mock, seed_data):
    ### Given ###
    mocker.patch("app.core.scheduler")

    # Mock ping calls for seeded accounts
    requests_mock.get("https://api.monzo.com/ping/whoami")
    requests_mock.get("https://api.truelayer.com/data/v1/me")

    # Mock pot balance call, returning 1000p (£10)
    requests_mock.get(
        "https://api.monzo.com/pots",
        json={"pots": [{"id": "pot_id", "balance": 1000, "deleted": False}]},
    )

    # Mock credit account balance calls, returning £9
    requests_mock.get(
        "https://api.truelayer.com/data/v1/cards",
        json={"results": [{"account_id": "card_id"}]},
    )
    requests_mock.get(
        "https://api.truelayer.com/data/v1/cards/card_id/balance",
        json={"results": [{"current": 9}]},
    )

    # Mock Monzo account balance call
    requests_mock.get(
        "https://api.monzo.com/accounts", json={"accounts": [{"id": "acc_id", "type": "uk_retail"}]}
    )
    requests_mock.get(
        "https://api.monzo.com/balance?account_id=acc_id", json={"balance": 100}
    )

    # Mock pot deposit call
    requests_mock.put("https://api.monzo.com/pots/pot_id/withdraw")

    ### When ###
    sync_balance()

    ### Then ###
    last_call = requests_mock.last_request.text
    assert "destination_account_id=acc_id" in last_call
    assert "amount=100" in last_call


def test_core_flow_insufficient_account_balance(
    mocker, test_client, requests_mock, seed_data
):
    ### Given ###
    mocker.patch("app.core.scheduler")

    # Mock ping calls for seeded accounts
    requests_mock.get("https://api.monzo.com/ping/whoami")
    requests_mock.get("https://api.truelayer.com/data/v1/me")

    # Mock pot balance call, returning 1000p (£10)
    requests_mock.get(
        "https://api.monzo.com/pots",
        json={"pots": [{"id": "pot_id", "balance": 1000, "deleted": False}]},
    )

    # Mock credit account balance calls, returning £1000
    requests_mock.get(
        "https://api.truelayer.com/data/v1/cards",
        json={"results": [{"account_id": "card_id"}]},
    )
    requests_mock.get(
        "https://api.truelayer.com/data/v1/cards/card_id/balance",
        json={"results": [{"current": 1000}]},
    )

    # Mock Monzo account balance call, returning £500
    requests_mock.get(
        "https://api.monzo.com/accounts", json={"accounts": [{"id": "acc_id", "type": "uk_retail"}]}
    )
    requests_mock.get(
        "https://api.monzo.com/balance?account_id=acc_id", json={"balance": 50000}
    )

    # Mock pot deposit call
    requests_mock.post("https://api.monzo.com/feed")

    ### When ###
    sync_balance()

    ### Then ###
    last_call = requests_mock.last_request.text
    assert "account_id=acc_id" in last_call
    assert "Insufficient" in last_call


def test_core_flow_no_monzo_account(mocker, test_client, requests_mock):
    ### Given ###
    mocker.patch("app.core.scheduler")

    ### When ###
    sync_balance()

    ### Then ###
    # No exceptions thrown
