from app.extensions import db
import json
from sqlalchemy.types import TypeDecorator, JSON
from sqlalchemy.ext.mutable import MutableDict

# Custom JSON type that coerces string values to a dict.
class CoerceJSON(TypeDecorator):
    impl = JSON

    def process_result_value(self, value, dialect):
        if value is None or value == "":
            return {}
        if isinstance(value, str):
            try:
                return json.loads(value)
            except Exception:
                return {}
        return value

class AccountModel(db.Model):
    type = db.Column(db.String(150), primary_key=True)
    pot_id = db.Column(db.String(150))
    access_token = db.Column(db.String(1024))
    refresh_token = db.Column(db.String(1024))
    token_expiry = db.Column(db.Integer)
    account_id = db.Column(db.String(150), nullable=True)
    cooldown_until = db.Column(db.Integer, nullable=True)
    # Use MutableDict and the CoerceJSON type so that any string values are converted to a dict.
    prev_balances = db.Column(MutableDict.as_mutable(CoerceJSON), default=lambda: {})