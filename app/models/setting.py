from app.extensions import db

class SettingModel(db.Model):
    key = db.Column(db.String, primary_key=True)
    value = db.Column(db.String(2048))

@db.event.listens_for(SettingModel.__table__, "after_create")
def after_create(target, connection, **kw):
    connection.execute(
        target.insert(),
        [
            {"key": "monzo_client_id", "value": ""},
            {"key": "monzo_client_secret", "value": ""},
            {"key": "truelayer_client_id", "value": ""},
            {"key": "truelayer_client_secret", "value": ""},
            {"key": "enable_sync", "value": "True"},
            {"key": "sync_interval_seconds", "value": "120"},
            {"key": "selected_account_id", "value": ""},  # Add this line
        ],
    )