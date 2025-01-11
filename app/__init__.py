import logging

from flask import Flask

from config import Config


def create_app():
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    logging.basicConfig(level=logging.INFO)

    from .core import sync_balance
    from .extensions import db, scheduler
    from .models import account as account
    from .models import setting as setting
    from .web import accounts_bp, auth_bp, home_bp, pots_bp, settings_bp

    db.init_app(app)
    # TODO move to migrations
    with app.app_context():
        db.create_all()

    app.register_blueprint(home_bp)
    app.register_blueprint(accounts_bp, url_prefix="/accounts")
    app.register_blueprint(pots_bp, url_prefix="/pots")
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(settings_bp, url_prefix="/settings")

    scheduler.init_app(app)
    scheduler.add_job(
        id="sync_balance", func=sync_balance, trigger="interval", seconds=120
    )
    scheduler.start()

    try:
        return app
    except Exception:
        scheduler.shutdown()
