import logging

from flask import Flask

from app.config import Config


def create_app(test_config=None):
    logging.basicConfig(level=logging.INFO)

    app = Flask(__name__, instance_relative_config=True)
    if test_config is None:
        app.config.from_object(Config)
    else:
        app.config.from_mapping(test_config)

    from .core import sync_balance
    from .extensions import db, scheduler
    from .models import account as account
    from .models import setting as setting

    db.init_app(app)
    # TODO move to migrations
    with app.app_context():
        db.create_all()

    from .web.accounts import accounts_bp
    from .web.auth import auth_bp
    from .web.home import home_bp
    from .web.pots import pots_bp
    from .web.settings import settings_bp

    app.register_blueprint(home_bp)
    app.register_blueprint(accounts_bp, url_prefix="/accounts")
    app.register_blueprint(pots_bp, url_prefix="/pots")
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(settings_bp, url_prefix="/settings")

    # don't need to setup the scheduler when testing, so return early
    if app.config["TESTING"]:
        return app

    scheduler.init_app(app)
    scheduler.add_job(
        id="sync_balance", func=sync_balance, trigger="interval", seconds=120
    )
    scheduler.start()

    try:
        return app
    except Exception:
        scheduler.shutdown()
