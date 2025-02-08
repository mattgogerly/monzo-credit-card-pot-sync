from sqlalchemy import Column, String, Integer

from app.extensions import db


class AccountModel(db.Model):
    __tablename__ = "account_model"

    id = Column(Integer, primary_key=True)
    type = Column(String, nullable=False)
    account_type = Column(String, nullable=False)  # New field
    access_token = Column(String, nullable=False)
    refresh_token = Column(String, nullable=False)
    token_expiry = Column(Integer, nullable=False)
    pot_id = Column(String, nullable=True)

    __table_args__ = (
        db.UniqueConstraint("type", "account_type", name="unique_account_type"),
    )
