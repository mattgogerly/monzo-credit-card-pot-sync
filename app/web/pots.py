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
    try:
        log.info("Retrieving Monzo account")
        monzo_account: MonzoAccount = account_repository.get_monzo_account()

        log.info("Retrieving pots for Monzo account")
        pots = monzo_account.get_pots()
    except NoResultFound:
        flash("You need to connect a Monzo account before you can view pots", "error")
        pots = []

    log.info(f"Retrieved {len(pots)} pots from Monzo")

    log.info("Retrieving credit card accounts")
    accounts = account_repository.get_credit_accounts()
    
    return render_template("pots/index.html", pots=pots, accounts=accounts)


@pots_bp.route("/", methods=["POST"])
def set_designated_pot():
    account_type = request.form["account_type"]
    account = account_repository.get(account_type)

    account.pot_id = request.form["pot_id"]
    account_repository.save(account)

    flash(f"Updated designated credit card pot for {account.type}")
    return redirect(url_for("pots.index"))
