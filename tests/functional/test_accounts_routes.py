def test_get_accounts(test_client, seed_data):
    response = test_client.get("/accounts/")
    assert response.status_code == 200
    assert b"Accounts" in response.data
    assert b"Monzo" in response.data
    # Check for a sample credit provider
    assert b"American Express" in response.data

# The joint account switching route has been removed.
# def test_switch_account_successful(test_client, seed_data):
#     # First, get the current Monzo account to confirm its initial state
#     response = test_client.get("/accounts/")
#     assert response.status_code == 200
#
#     # This route no longer exists; joint account configuration is now managed in pots
#     response = test_client.post("/accounts/switch", data={"selected_account_id": "joint_123"})
#     # Expect a redirect back to the index
#     assert response.status_code == 302
#
#     # Optionally, re-fetch and check if the account now displays the joint account info.

def test_get_accounts_no_accounts(test_client):
    response = test_client.get("/accounts/")
    assert response.status_code == 200
    assert b"Accounts" in response.data