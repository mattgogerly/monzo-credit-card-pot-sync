import logging
from flask import Blueprint, flash, redirect, render_template, request, url_for
from sqlalchemy.exc import NoResultFound

from app.domain.accounts import MonzoAccount
from app.extensions import db
from app.models.account_repository import SqlAlchemyAccountRepository

pots_bp = Blueprint("pots", __name__)

log = logging.getLogger("pots")
account_repository = SqlAlchemyAccountRepository(db)

@pots_bp.route("/", methods=["GET"])
def index():
    # Use query parameter "account" to determine display mode, defaulting to personal
    account_type = request.args.get("account", "personal")
    try:
        log.info(f"Retrieving Monzo account for {account_type} account")
        monzo_account: MonzoAccount = account_repository.get_monzo_account()
        # Pass the account type to get_pots so that the joint account is used when selected
        pots = monzo_account.get_pots(account_type)
    except NoResultFound:
        flash("You need to connect a Monzo account before you can view pots", "error")
        pots = []

    log.info(f"Retrieved {len(pots)} pots from Monzo")
    log.info("Retrieving credit card accounts")
    accounts = account_repository.get_credit_accounts()
    
    return render_template("pots/index.html", pots=pots, accounts=accounts, account_type=account_type)

@pots_bp.route("/", methods=["POST"])
def set_designated_pot():
    account_type = request.form.get("account_type")
    pot_id = request.form.get("pot_id")
    selected_account_type = request.form.get("selected_account_type")

    account = account_repository.get(account_type)
    account.pot_id = pot_id
    account.account_selection = selected_account_type  # Update the account selection
    account_repository.save(account)

    flash(f"Updated designated credit card pot for {account.type}")
    return redirect(url_for("pots.index"))