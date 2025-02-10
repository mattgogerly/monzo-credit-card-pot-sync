from urllib.parse import urlparse

def test_get_pots(test_client, requests_mock, seed_data):
    requests_mock.get(
        "https://api.monzo.com/accounts",
        json={"accounts": [{"id": "acc_123", "type": "uk_retail", "currency": "GBP"}]},
    )
    requests_mock.get(
        "https://api.monzo.com/pots?current_account_id=acc_123",
        json={
            "pots": [
                {"id": "pot_123", "name": "Pot 1", "balance": 100, "deleted": False}
            ]
        },
    )
    response = test_client.get("/pots/")
    assert response.status_code == 200
    assert b"Pot 1" in response.data

def test_get_pots_no_account(test_client):
    response = test_client.get("/pots/")
    assert response.status_code == 200
    assert b"You need to connect a Monzo account" in response.data

def test_post_pots(test_client, requests_mock):
    # Mock necessary external calls
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

    # Mock pending transactions call, returning no pending transactions
    requests_mock.get(
        "https://api.truelayer.com/data/v1/cards/card_id/transactions/pending",
        json={"results": []},
    )

    # Mock Monzo account balance call with additional account details
    requests_mock.get(
        "https://api.monzo.com/accounts",
        json={"accounts": [{"id": "acc_id", "type": "uk_retail", "currency": "GBP"}]},
    )
    requests_mock.get(
        "https://api.monzo.com/balance?account_id=acc_id", json={"balance": 50000}
    )

    # Mock a post to the feed for insufficient funds notification
    requests_mock.post("https://api.monzo.com/feed")

    # Perform the POST request to set the designated pot
    response = test_client.post(
        "/set_designated_pot",
        data={
            "account_type": "credit",
            "pot_id": "pot_id",
            "selected_account_type": "personal"
        }
    )

    # Assert that the response status code is 302 (redirect)
    assert response.status_code == 302