from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.extensions import db
from app.models.setting_repository import SqlAlchemySettingRepository
import requests

switch_bp = Blueprint("switch", __name__)

def get_monzo_accounts(access_token):
    url = "https://api.monzo.com/accounts"
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        accounts_data = response.json()
        return accounts_data.get("accounts", [])
    else:
        print(f"Error fetching accounts: {response.status_code} - {response.text}")
        return []

@switch_bp.route("/", methods=["GET", "POST"])
def select_account():
    # Retrieve the access token from your settings or environment
    setting_repo = SqlAlchemySettingRepository(db)
    access_token = setting_repo.get("monzo_access_token")
    
    accounts = get_monzo_accounts(access_token)
    selected_account_id = setting_repo.get("selected_account_id")
    
    if request.method == "POST":
        account_id = request.form.get("account_id")
        if account_id:
            setting_repo.set("selected_account_id", account_id)
            flash("Account selection updated.", "success")
            return redirect(url_for("switch.select_account"))
        else:
            flash("Please select an account.", "error")
    
    return render_template("switch/index.html", accounts=accounts, selected_account_id=selected_account_id)
