from app.extensions import db


class AccountModel(db.Model):
    type = db.Column(db.String(150), primary_key=True)
    access_token = db.Column(db.String(1024))
    refresh_token = db.Column(db.String(1024))
    token_expiry = db.Column(db.Integer)
