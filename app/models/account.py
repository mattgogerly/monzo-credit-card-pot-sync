from app.extensions import db

class AccountModel(db.Model):
    __tablename__ = 'accounts'

    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(50), nullable=False)
    access_token = db.Column(db.String(255), nullable=False)
    refresh_token = db.Column(db.String(255), nullable=True)
    token_expiry = db.Column(db.Integer, nullable=True)
    pot_id = db.Column(db.String(255), nullable=True)
    account_id = db.Column(db.String(255), nullable=True)
    account_selection = db.Column(db.String(50), nullable=True)