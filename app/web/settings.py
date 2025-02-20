import logging
from flask import Blueprint, flash, redirect, render_template, request, url_for
from app.domain.settings import Setting
from app.extensions import db, scheduler
from app.models.setting_repository import SqlAlchemySettingRepository

settings_bp = Blueprint("settings", __name__)

log = logging.getLogger("settings")
repository = SqlAlchemySettingRepository(db)

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
    except Exception:
        log.exception("Failed to save settings")
        flash("Error saving settings, check logs for more details", "error")

    return redirect(url_for("settings.index"))