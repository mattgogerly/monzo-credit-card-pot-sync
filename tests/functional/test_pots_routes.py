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


def test_get_pots_joint_account(test_client, requests_mock, seed_data):
    requests_mock.get(
        "https://api.monzo.com/accounts",
        json={"accounts": [{"id": "acc_456", "type": "uk_retail_joint", "currency": "GBP"}]},
    )
    requests_mock.get(
        "https://api.monzo.com/pots?current_account_id=acc_456",
        json={
            "pots": [
                {"id": "pot_456", "name": "Joint Pot", "balance": 200, "deleted": False}
            ]
        },
    )
    response = test_client.get("/pots/")
    assert response.status_code == 200
    assert b"Joint Pot" in response.data


def test_post_pots_joint_account(test_client, requests_mock, seed_data):
    response = test_client.post(
        "/pots/", data={"account_type": "uk_retail_joint", "pot_id": "pot_456"}
    )
    assert response.status_code == 302
    assert urlparse(response.location).path == "/pots/"

    requests_mock.get(
        "https://api.monzo.com/accounts",
        json={"accounts": [{"id": "acc_456", "type": "uk_retail_joint", "currency": "GBP"}]},
    )
    requests_mock.get(
        "https://api.monzo.com/pots?current_account_id=acc_456",
        json={
            "pots": [
                {"id": "pot_456", "name": "Joint Pot", "balance": 200, "deleted": False}
            ]
        },
    )
    response = test_client.get("/pots/")
    assert response.status_code == 200
    assert b"Joint Pot" in response.data
