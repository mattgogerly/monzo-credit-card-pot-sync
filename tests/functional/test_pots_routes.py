def test_post_pots(test_client, requests_mock, db_session):
    # Create a credit account in the database
    credit_account = AccountModel(
        type="credit",
        access_token="test_access_token",
        refresh_token="test_refresh_token",
        token_expiry=1234567890,
        pot_id=None,
        account_id="test_account_id"
    )
    db_session.add(credit_account)
    db_session.commit()

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
        "/pots/set_designated_pot",
        data={
            "account_type": "credit",
            "pot_id": "pot_id",
            "selected_account_type": "personal"
        }
    )

    # Assert that the response status code is 302 (redirect)
    assert response.status_code == 302