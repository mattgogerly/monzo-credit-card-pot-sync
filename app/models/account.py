from app.extensions import db
from sqlalchemy.ext.mutable import MutableDict

class AccountModel(db.Model):
    type = db.Column(db.String(150), primary_key=True)
    pot_id = db.Column(db.String(150))
    access_token = db.Column(db.String(1024))
    refresh_token = db.Column(db.String(1024))
    token_expiry = db.Column(db.Integer)
    account_id = db.Column(db.String(150), nullable=True)
    cooldown_until = db.Column(db.Integer, nullable=True)
    # Use MutableDict so changes in the dict are tracked and persisted.
    prev_balances = db.Column(MutableDict.as_mutable(db.JSON), default=lambda: {})