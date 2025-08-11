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
    from .models.setting_repository import SqlAlchemySettingRepository  # Removed unused imports

    db.init_app(app)
    # Create tables (if migrations are not yet set up)
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

    # Skip scheduler setup when testing
    if app.config["TESTING"]:
        return app

    # Retrieve the configured interval for the sync loop
    with app.app_context():
        setting_repository = SqlAlchemySettingRepository(db)
        interval = setting_repository.get("sync_interval_seconds")

    scheduler.init_app(app)
    scheduler.add_job(
        id="sync_balance", func=sync_balance, trigger="interval", seconds=int(interval)
    )
    scheduler.start()

    return app