from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class AuthException(Exception):
    """Custom exception for authentication errors."""
    pass