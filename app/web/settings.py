import logging

from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.domain.settings import Setting
from app.extensions import db
from app.models.setting_repository import SqlAlchemySettingRepository

settings_bp = Blueprint("settings", __name__)

log = logging.getLogger("settings")
repository = SqlAlchemySettingRepository(db)


@settings_bp.route("/", methods=["GET"])
def index():
    settings = {s.key: s.value for s in repository.get_all()}
    return render_template("settings/index.html", settings=settings)


@settings_bp.route("/", methods=["POST"])
def save():
    try:
        # POST request doesn't include a checkbox if unchecked, so we need to do some
        # wrangling here to determine if the enable_sync setting should be true or false
        if request.form.get("enable_sync") is not None:
            repository.save(Setting("enable_sync", "True"))
        else:
            repository.save(Setting("enable_sync", "False"))

        for key, val in request.form.items():
            # special case handled above
            if key == "enable_sync":
                continue

            repository.save(Setting(key, val))

        flash("Settings saved")
    except Exception as e:
        log.exception("Failed to save settings", e)
        flash("Error saving settings, check logs for more details", "error")

    return redirect(url_for("settings.index"))
