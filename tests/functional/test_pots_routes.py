from urllib.parse import urlparse
from app.models.account import AccountModel

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

def test_post_pots(test_client, requests_mock, seed_data):
    # Ensure only one account of each type is created
    AccountModel.query.delete()
    db.session.commit()

    # Create a credit account in the database
    credit_account = AccountModel(
        type="American Express",
        access_token="test_access_token",
        refresh_token="test_refresh_token",
        token_expiry=1234567890,
        pot_id=None,
        account_id="test_account_id"
    )
    db.session.add(credit_account)
    db.session.commit()

    # Submit a request to set the designated pot for a given credit card account
    response = test_client.post(
        "/pots/", data={"account_type": "American Express", "pot_id": "pot_123"}
    )
    assert response.status_code == 302
    assert urlparse(response.location).path == "/pots/"

    # Following the update, fetch the pots page to verify changes are reflected.
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
    # Verify that the designated pot indicator appears as expected
    assert b"Credit Card pot" in response.data