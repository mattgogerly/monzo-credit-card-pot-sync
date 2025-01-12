from flask import Blueprint, flash, redirect, render_template, request, url_for
from sqlalchemy.exc import NoResultFound

from app.domain.auth_providers import AuthProviderType, provider_mapping
from app.extensions import db
from app.models.account_repository import SqlAlchemyAccountRepository

accounts_bp = Blueprint("accounts", __name__)

account_repository = SqlAlchemyAccountRepository(db)


@accounts_bp.route("/", methods=["GET"])
def index():
    accounts = account_repository.get_all()
    return render_template("accounts/index.html", accounts=accounts)


@accounts_bp.route("/add", methods=["GET"])
def add_account():
    monzo_provider = provider_mapping[AuthProviderType.MONZO]
    credit_providers = dict(
        [
            (i, provider_mapping[i])
            for i in provider_mapping
            if i is not AuthProviderType.MONZO
        ]
    )
    return render_template(
        "accounts/add.html",
        monzo_provider=monzo_provider,
        credit_providers=credit_providers,
    )


@accounts_bp.route("/", methods=["POST"])
def delete_account():
    account_type = request.form["account_type"]
    try:
        account_repository.delete(account_type)
        flash("Account deleted")
    except NoResultFound:
        pass

    return redirect(url_for("accounts.index"))
