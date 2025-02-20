from app.extensions import db
from sqlalchemy import Column, Integer, String  # ...existing imports...

class AccountModel(db.Model):
    __tablename__ = "accounts"
    id = Column(Integer, primary_key=True)
    type = Column(String(50), nullable=False)
    access_token = Column(String(255), nullable=False)
    refresh_token = Column(String(255), nullable=False)
    token_expiry = Column(Integer)
    pot_id = Column(String(255))
    account_id = Column(String(255))
    cooldown_until = Column(Integer, nullable=True)
    prev_balance = Column(Integer, default=0)
    cooldown_start_balance = Column(Integer, nullable=True)  # new field
    pending_drop = Column(Integer, nullable=True)  # new field