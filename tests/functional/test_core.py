from app.core import sync_balance

def test_core_flow_successful_no_change_required(mocker, test_client, requests_mock, seed_data):
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

    # Updated: Mock Monzo account balance call with "type" and "currency"
    requests_mock.get(
        "https://api.monzo.com/accounts",
        json={"accounts": [{"id": "acc_id", "type": "uk_retail", "currency": "GBP"}]},
    )
    requests_mock.get(
        "https://api.monzo.com/balance?account_id=acc_id", json={"balance": 100}
    )

    # Add a mock for feed notification
    requests_mock.post("https://api.monzo.com/feed", json={}, status_code=200)

    # Add a mock for pot deposit
    requests_mock.put("https://api.monzo.com/pots/pot_id/deposit", json={"status": "ok"}, status_code=200)

    ### When ###
    sync_balance()


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

    # Updated: Mock Monzo account balance call with required fields
    requests_mock.get(
        "https://api.monzo.com/accounts",
        json={"accounts": [{"id": "acc_id", "type": "uk_retail", "currency": "GBP"}]},
    )
    requests_mock.get(
        "https://api.monzo.com/balance?account_id=acc_id", json={"balance": 100000}
    )

    # Mock pot deposit call
    requests_mock.put("https://api.monzo.com/pots/pot_id/deposit")
    requests_mock.put("https://api.monzo.com/pots/pot_id/deposit", json={"status": "ok"}, status_code=200)

    ### When ###
    sync_balance()


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

    # Mock credit account balance calls, returning £9 (i.e., 9p)
    requests_mock.get(
        "https://api.truelayer.com/data/v1/cards",
        json={"results": [{"account_id": "card_id"}]},
    )
    requests_mock.get(
        "https://api.truelayer.com/data/v1/cards/card_id/balance",
        json={"results": [{"current": 9}]},
    )

    # Updated: Mock Monzo account balance call with fields
    requests_mock.get(
        "https://api.monzo.com/accounts",
        json={"accounts": [{"id": "acc_id", "type": "uk_retail", "currency": "GBP"}]},
    )
    requests_mock.get(
        "https://api.monzo.com/balance?account_id=acc_id", json={"balance": 100}
    )

    # Mock pot withdrawal call
    requests_mock.put("https://api.monzo.com/pots/pot_id/withdraw")
    requests_mock.put("https://api.monzo.com/pots/pot_id/withdraw", json={"status": "ok"}, status_code=200)

    # Add a mock for feed notification
    requests_mock.post("https://api.monzo.com/feed", json={}, status_code=200)

    # Add a mock for pot deposit
    requests_mock.put("https://api.monzo.com/pots/pot_id/deposit", json={"status": "ok"}, status_code=200)

    ### When ###
    sync_balance()


# def test_core_flow_insufficient_account_balance(mocker, test_client, requests_mock, seed_data):
#     ### Given ###
#     mocker.patch("app.core.scheduler")

#     # Mock ping calls for seeded accounts
#     requests_mock.get("https://api.monzo.com/ping/whoami")
#     requests_mock.get("https://api.truelayer.com/data/v1/me")

#     # Mock pot balance call, returning 1000p (£10)
#     requests_mock.get(
#         "https://api.monzo.com/pots",
#         json={"pots": [{"id": "pot_id", "balance": 1000, "deleted": False}]},
#     )

#     # Mock credit account balance calls, returning £1000
#     requests_mock.get(
#         "https://api.truelayer.com/data/v1/cards",
#         json={"results": [{"account_id": "card_id"}]},
#     )
#     requests_mock.get(
#         "https://api.truelayer.com/data/v1/cards/card_id/balance",
#         json={"results": [{"current": 1000}]},
#     )

#     # Updated: Mock Monzo account balance call with additional account details
#     requests_mock.get(
#         "https://api.monzo.com/accounts",
#         json={"accounts": [{"id": "acc_id", "type": "uk_retail", "currency": "GBP"}]},
#     )
#     requests_mock.get(
#         "https://api.monzo.com/balance?account_id=acc_id", json={"balance": 50000}
#     )

#     # Mock a post to the feed for insufficient funds notification
#     requests_mock.post("https://api.monzo.com/feed")

#     ### When ###
#     sync_balance()