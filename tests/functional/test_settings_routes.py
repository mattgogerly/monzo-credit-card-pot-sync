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

def test_settings_index(test_client, monkeypatch):
    dummy_settings = [
        type("DummySetting", (), {"key": "monzo_client_id", "value": "test_id"}),
        type("DummySetting", (), {"key": "enable_sync", "value": "True"}),
    ]
    monkeypatch.setattr("app.web.settings.repository.get_all", lambda: dummy_settings)
    with test_client.application.test_request_context():
        url = url_for("settings.index")
    response = test_client.get(url)
    assert response.status_code == 200
    assert b"test_id" in response.data

def test_settings_save_success(test_client, monkeypatch):
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
    monkeypatch.setattr("app.web.settings.repository.get_all", lambda: [type("S", (), s) for s in [
        {"key": k, "value": v} for k, v in dummy_settings.items()
    ]])
    monkeypatch.setattr("app.web.settings.repository.save", lambda setting: None)
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
    with test_client.application.test_request_context():
        url = url_for("settings.save")
    response = test_client.post(url, data=form_data, follow_redirects=True)
    assert response.status_code == 200
    assert b"Settings saved" in response.data

def test_settings_save_error(test_client, monkeypatch):
    # Define a side-effect function that raises an exception only on the first call.
    def side_effect():
        if not hasattr(side_effect, "called"):
            side_effect.called = True
            raise Exception("Forced error")
        else:
            # Return dummy settings for subsequent calls (e.g. in the index view)
            return [
                type("DummySetting", (), {"key": "monzo_client_id", "value": "default_id"}),
                type("DummySetting", (), {"key": "enable_sync", "value": "False"}),
            ]
    monkeypatch.setattr("app.web.settings.repository.get_all", side_effect)
    with test_client.application.test_request_context():
        url = url_for("settings.save")
    response = test_client.post(url, data={}, follow_redirects=True)
    assert response.status_code == 200
    # The flashed message should indicate an error saving settings.
    assert b"Error saving settings" in response.data