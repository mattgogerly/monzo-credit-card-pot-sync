from flask import render_template

from app.web import home_bp


@home_bp.route("/", methods=["GET"])
def index():
    return render_template("index.html")
