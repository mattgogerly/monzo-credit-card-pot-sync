import logging
from flask import Blueprint, flash, redirect, render_template, request, url_for
from time import time
from app.domain.settings import Setting
from app.extensions import db, scheduler
from app.models.setting_repository import SqlAlchemySettingRepository
from app.models.account_repository import SqlAlchemyAccountRepository

settings_bp = Blueprint("settings", __name__)

log = logging.getLogger("settings")
repository = SqlAlchemySettingRepository(db)
account_repository = SqlAlchemyAccountRepository(db)

@settings_bp.route("/", methods=["GET"])
def index():
    settings = {s.key: s.value for s in repository.get_all()}
    # Pass settings as 'data' for compatibility with the template
    return render_template("settings/index.html", data=settings)

@settings_bp.route("/", methods=["POST"])
def save():
    try:
        current_settings = {s.key: s.value for s in repository.get_all()}

        # Checkbox: POST request omits unchecked boxes, so set value accordingly
        if request.form.get("enable_sync") is not None:
            repository.save(Setting("enable_sync", "True"))
        else:
            repository.save(Setting("enable_sync", "False"))

        # Checkbox: POST request omits unchecked boxes, so set value accordingly
        if request.form.get("override_cooldown_spending") is not None:
            repository.save(Setting("override_cooldown_spending", "True"))
        else:
            repository.save(Setting("override_cooldown_spending", "False"))

        for key, val in request.form.items():
            if key in ["enable_sync", "override_cooldown_spending"]:
                continue

            if current_settings.get(key) != val:
                repository.save(Setting(key, val))

                if key == "sync_interval_seconds":
                    scheduler.modify_job(id="sync_balance", trigger="interval", seconds=int(val))

        flash("Settings saved")
    except Exception as e:
        log.error("Failed to save settings", exc_info=e)
        flash("Error saving settings", "error")

    return redirect(url_for("settings.index"))

@settings_bp.route("/clear_cooldown", methods=["POST"])
def clear_cooldown():
    # Clear cooldown by setting cooldown_until to 10 minutes in the past
    now_minus_10 = int(time()) - 600
    credit_accounts = account_repository.get_credit_accounts()
    for account in credit_accounts:
        account.cooldown_until = now_minus_10
        # Update prev_balance to the current live balance
        account.prev_balance = account.get_total_balance()
        account_repository.save(account)
    flash("Cooldown cleared—baseline updated.")
    return redirect(url_for("settings.index"))