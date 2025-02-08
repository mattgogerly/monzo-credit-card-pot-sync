from flask import Blueprint, render_template

switch_bp = Blueprint("switch", __name__)

@switch_bp.route("/")
def switch_home():
    return render_template("switch.html")