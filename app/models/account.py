from app.extensions import db


class AccountModel(db.Model):
    __tablename__ = "accounts"

    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(150), nullable=False)
    pot_id = db.Column(db.String(150), nullable=True)
    access_token = db.Column(db.String(1024), nullable=False)
    refresh_token = db.Column(db.String(1024), nullable=False)
    token_expiry = db.Column(db.Integer)
    account_id = db.Column(db.String(1024), nullable=True)  # Add this line