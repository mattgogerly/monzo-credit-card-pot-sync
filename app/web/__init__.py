from flask import Blueprint

from app.web import accounts as accounts
from app.web import auth as auth
from app.web import home as home
from app.web import pots as pots
from app.web import settings as settings

home_bp = Blueprint("home", __name__)
accounts_bp = Blueprint("accounts", __name__)
pots_bp = Blueprint("pots", __name__)
auth_bp = Blueprint("auth", __name__)
settings_bp = Blueprint("settings", __name__)
