from flask import url_for
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

def test_settings_post_override_cooldown(test_client, seed_data):
    response = test_client.post("/settings/", data={"override_cooldown_spending": "on"})
    assert response.status_code == 302

    response = test_client.get("/settings/")
    assert b"Override Cooldown Spending" in response.data
    # ...verify it shows as checked or stored...

def test_settings_index(client, monkeypatch):
    # Ensure GET returns proper template with settings data
    # Monkey-patch repository.get_all() to return dummy settings.
    dummy_settings = [
        type("DummySetting", (), {"key": "monzo_client_id", "value": "test_id"}),
        type("DummySetting", (), {"key": "enable_sync", "value": "True"}),
    ]
    monkeypatch.setattr("app.web.settings.repository.get_all", lambda: dummy_settings)
    response = client.get(url_for("settings.index"))
    assert response.status_code == 200
    assert b"test_id" in response.data

def test_settings_save_success(client, monkeypatch):
    # Test POST success: both checkboxes checked, and an extra field changes.
    dummy_settings = {
        "monzo_client_id": "id_old",
        "monzo_client_secret": "secret_old",
        "truelayer_client_id": "tl_old",
        "truelayer_client_secret": "tl_secret_old",
        "enable_sync": "False",
        "sync_interval_seconds": "120",
        "deposit_cooldown_hours": "3",
        "override_cooldown_spending": "False"
    }
    # Patch repository.get_all to return dummy settings as Domain objects.
    monkeypatch.setattr("app.web.settings.repository.get_all", lambda: [type("S", (), s) for s in [
        {"key": k, "value": v} for k, v in dummy_settings.items()
    ]])
    # Patch repository.save as a no-op.
    monkeypatch.setattr("app.web.settings.repository.save", lambda setting: None)
    # Patch scheduler.modify_job as a no-op.
    monkeypatch.setattr("app.web.settings.scheduler.modify_job", lambda **kwargs: None)

    form_data = {
        "monzo_client_id": "id_new",
        "monzo_client_secret": "secret_new",
        "truelayer_client_id": "tl_new",
        "truelayer_client_secret": "tl_secret_new",
        "sync_interval_seconds": "180",
        "deposit_cooldown_hours": "2",
        "enable_sync": "on",
        "override_cooldown_spending": "on",
    }
    response = client.post(url_for("settings.save"), data=form_data, follow_redirects=True)
    assert response.status_code == 200
    # Expect success flash message
    assert b"Settings saved" in response.data

def test_settings_save_error(client, monkeypatch):
    # Force an exception in the POST route to trigger error flash message.
    def raise_exception():
        raise Exception("Forced error")
    monkeypatch.setattr("app.web.settings.repository.get_all", lambda: raise_exception())
    response = client.post(url_for("settings.save"), data={}, follow_redirects=True)
    assert response.status_code == 200
    assert b"Error saving settings" in response.data