from time import time

from flask import Blueprint, flash, redirect, request, url_for

from app.domain.accounts import MonzoAccount, TrueLayerAccount
from app.domain.auth_providers import (
    AuthProviderType,
    MonzoAuthProvider,
    provider_mapping,
)
from app.extensions import db
from app.models.account_repository import SqlAlchemyAccountRepository

auth_bp = Blueprint("auth", __name__)

account_repository = SqlAlchemyAccountRepository(db)


@auth_bp.route("/callback/monzo", methods=["GET"])
def monzo_callback():
    code = request.args.get("code")
    tokens = MonzoAuthProvider().handle_oauth_code_callback(code)

    account = MonzoAccount(
        tokens["access_token"],
        tokens["refresh_token"],
        int(time()) + tokens["expires_in"],
        pot_id="default_pot"  # Provide a default pot ID
    )
    account_repository.save(account)

    flash(f"Successfully linked {account.type}")
    return redirect(url_for("accounts.index"))


@auth_bp.route("/callback/truelayer", methods=["GET"])
def truelayer_callback():
    provider_type = request.args.get("state").split("-")[0]
    provider = provider_mapping[AuthProviderType(provider_type)]

    code = request.args.get("code")
    tokens = provider.handle_oauth_code_callback(code)
    account = TrueLayerAccount(
        provider.name,
        tokens["access_token"],
        tokens["refresh_token"],
        int(time()) + tokens["expires_in"],
        pot_id="default_pot"  # Provide a default pot ID
    )
    account_repository.save(account)

    flash(f"Successfully linked {account.type}")
    return redirect(url_for("accounts.index"))