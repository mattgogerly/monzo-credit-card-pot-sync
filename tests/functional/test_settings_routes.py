from urllib.parse import urlparse


def test_settings_get(test_client, seed_data):
    response = test_client.get("/settings/")
    assert response.status_code == 200
    assert b"Settings" in response.data
    assert b"Monzo Client ID" in response.data
    assert b"Monzo Client Secret" in response.data
    assert b"TrueLayer Client ID" in response.data
    assert b"TrueLayer Client Secret" in response.data
    assert b"Sync Interval" in response.data
    assert b"Enable Balance Sync" in response.data


def test_settings_post(test_client, seed_data):
    response = test_client.post("/settings/", data={"monzo_client_id": "123"})
    assert response.status_code == 302
    assert urlparse(response.location).path == "/settings/"

    response = test_client.get("/settings/")
    assert b"Monzo Client ID" in response.data
    assert b"123" in response.data
