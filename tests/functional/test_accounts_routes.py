def test_get_accounts(test_client, seed_data):
    response = test_client.get("/accounts/")
    assert response.status_code == 200
    assert b"Accounts" in response.data
    assert b"Monzo" in response.data
    # Check for a sample credit provider
    assert b"American Express" in response.data

def test_get_accounts_no_accounts(test_client):
    response = test_client.get("/accounts/")
    assert response.status_code == 200
    assert b"Accounts" in response.data