from flask import flash, redirect, render_template, request, url_for
from sqlalchemy.exc import NoResultFound

from app.domain.accounts import MonzoAccount
from app.domain.settings import Setting
from app.extensions import db
from app.models.account_repository import SqlAlchemyAccountRepository
from app.models.setting_repository import SqlAlchemySettingRepository
from app.web import pots_bp

account_repository = SqlAlchemyAccountRepository(db)
setting_repository = SqlAlchemySettingRepository(db)


@pots_bp.route("/", methods=["GET"])
def index():
    try:
        monzo_account: MonzoAccount = account_repository.get_monzo_account()
        pots = monzo_account.get_pots()
    except NoResultFound:
        flash("You need to connect a Monzo account before you can view pots", "error")
        pots = []

    designated_pot_id = setting_repository.get("credit_card_pot_id")
    return render_template(
        "pots/index.html", pots=pots, designated_pot_id=designated_pot_id
    )


@pots_bp.route("/", methods=["POST"])
def set_designated_pot():
    pot_id = request.form["pot_id"]
    setting_repository.save(Setting("credit_card_pot_id", pot_id))
    flash("Updated designated credit card pot")
    return redirect(url_for("pots.index"))
