from app.extensions import db


class SettingModel(db.Model):
    key = db.Column(db.String, primary_key=True)
    value = db.Column(db.String(2048))


@db.event.listens_for(SettingModel.__table__, "after_create")
def after_create(tbl, conn, **kw) -> None:
    conn.execute(
        tbl.insert(),
        [
            {"key": "monzo_client_id", "value": ""},
            {"key": "monzo_client_secret", "value": ""},
            {"key": "truelayer_client_id", "value": ""},
            {"key": "truelayer_client_secret", "value": ""},
            {"key": "credit_card_pot_id", "value": ""},
            {"key": "enable_sync", "value": True},
            {"key": "sync_interval_seconds", "value": 120},
        ],
    )
