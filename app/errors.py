from flask_sqlalchemy import SQLAlchemy
from flask_apscheduler import APScheduler

db = SQLAlchemy()

class AuthException(Exception):
    """Custom exception for authentication errors."""
    pass