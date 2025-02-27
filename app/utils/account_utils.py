import datetime
import time
from app.models.account import AccountModel

def get_cooldown_for_pot(pot_id: str, session) -> str:
    """
    Look up the account with the given pot_id and return the active cooldown
    formatted as 'YYYY-MM-DD HH:mm:ss'. Returns None if no active cooldown.
    """
    account = session.query(AccountModel).filter_by(pot_id=pot_id).first()
    if account and account.cooldown_until and account.cooldown_until > int(time.time()):
        return datetime.datetime.fromtimestamp(account.cooldown_until).strftime("%Y-%m-%d %H:%M:%S")
    return None
