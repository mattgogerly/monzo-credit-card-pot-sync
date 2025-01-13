def test_settings_get(test_client, seed_data):
    response = test_client.get("/settings/")
    assert response.status_code == 200
    assert b"Settings" in response.data
    assert b"Monzo Client ID" in response.data
    assert b"Monzo Client Secret" in response.data
    assert b"TrueLayer Client ID" in response.data
    assert b"TrueLayer Client Secret" in response.data