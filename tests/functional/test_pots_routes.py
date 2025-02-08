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


def test_get_pots_no_account(test_client, mocker):
    # Mock the account_repository to raise NoResultFound
    mocker.patch('app.models.account_repository.SqlAlchemyAccountRepository.get_all_monzo_accounts', side_effect=NoResultFound)
    
    response = test_client.get("/pots/")
    assert response.status_code == 200
    assert b"You need to connect a Monzo account" in response.data


def test_post_pots(test_client, requests_mock, seed_data):
    response = test_client.post(
        "/pots/", data={"account_type": "American Express", "pot_id": "pot_123"}
    )
    assert response.status_code == 302
    assert urlparse(response.location).path == "/pots/"

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
    assert b"Credit Card pot" in response.data
