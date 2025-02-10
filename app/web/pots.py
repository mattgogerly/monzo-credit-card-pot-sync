from flask import Blueprint, request, render_template, redirect, url_for, flash
from app.models.account_repository import SqlAlchemyAccountRepository
from app.extensions import db
from sqlalchemy.orm.exc import NoResultFound

pots_bp = Blueprint('pots', __name__)
account_repository = SqlAlchemyAccountRepository(db.session)

@pots_bp.route("/", methods=["GET"])
def index():
    # Render the index template for the pots blueprint
    return render_template("pots/index.html")

@pots_bp.route("/set_designated_pot", methods=["POST"])
def set_designated_pot():
    account_type = request.form.get("account_type")
    pot_id = request.form.get("pot_id")
    selected_account_type = request.form.get("selected_account_type")

    try:
        account = account_repository.get(account_type)
        account.pot_id = pot_id
        account.account_selection = selected_account_type
        account_repository.save(account)
        flash(f"Updated designated credit card pot for {account.type}")
    except NoResultFound:
        flash(f"Account of type {account_type} not found", "error")

    return redirect(url_for("pots.index", account=selected_account_type))