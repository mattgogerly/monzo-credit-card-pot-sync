from app.extensions import db
from sqlalchemy import Column, Integer, String

class AccountModel(db.Model):
    id = Column(Integer, primary_key=True)
    type = Column(String(50), nullable=False, unique=True)
    access_token = Column(String(255), nullable=False)
    refresh_token = Column(String(255), nullable=False)
    token_expiry = Column(Integer)
    pot_id = Column(String(255))
    account_id = Column(String(255))
    cooldown_until = Column(Integer, nullable=True)
    prev_balance = Column(Integer, default=0)
    cooldown_start_balance = Column(Integer, nullable=True)
    last_cooldown_expired = Column(Integer, nullable=True)
    pending_drop = Column(Integer, nullable=True)
    pot_snapshot_balance = Column(Integer, nullable=True, default=0)
    pot_snapshot_timestamp = Column(Integer, nullable=True)
    cooldown_ref_card_balance = Column(Integer, default=0)
    cooldown_ref_pot_balance = Column(Integer, default=0)