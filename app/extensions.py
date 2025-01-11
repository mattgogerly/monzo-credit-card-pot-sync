from flask_apscheduler import APScheduler
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
scheduler = APScheduler()
