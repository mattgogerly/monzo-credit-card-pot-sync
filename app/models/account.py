from app.extensions import db
import json
from sqlalchemy.types import TypeDecorator, JSON

class AccountModel(db.Model):
    type = db.Column(db.String(150), primary_key=True)
    pot_id = db.Column(db.String(150))
    access_token = db.Column(db.String(1024))
    refresh_token = db.Column(db.String(1024))
    token_expiry = db.Column(db.Integer)
    account_id = db.Column(db.String(150), nullable=True)
    cooldown_until = db.Column(db.Integer, nullable=True)
    prev_balance = db.Column(db.Integer, default=0)