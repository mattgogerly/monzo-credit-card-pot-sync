import logging
from sqlalchemy.exc import NoResultFound
from time import time
import datetime  # Add import if not already present

from app.errors import AuthException
from app.domain.settings import Setting
from app.extensions import db, scheduler
from app.models.account_repository import SqlAlchemyAccountRepository
from app.models.setting_repository import SqlAlchemySettingRepository

log = logging.getLogger("core")

account_repository = SqlAlchemyAccountRepository(db)
settings_repository = SqlAlchemySettingRepository(db)

def sync_balance():
    """
    Main sync entry point: processes each credit account in turn.
    1) Refresh tokens & check health
    2) Get pot & card balances
    3) If no cooldown is active:
       - If card balance increased, deposit difference.
       - If card balance decreased, withdraw difference.
       - If pot dropped (no matching card drop), start cooldown.
    4) If cooldown is active:
       - If card goes up, deposit difference (override mode).
       - End cooldown if pot & card match or if cooldown expired.
         If expired & pot < card, top-up the shortfall.
    5) Log each action for clarity and debugging.
    """
    with scheduler.app.app_context():
        # Attempt to load a Monzo account if present
        monzo_account = None
        try:
            log.info("Loading Monzo account (if any)")
            monzo_account = account_repository.get_monzo_account()
            if (monzo_account.is_token_within_expiry_window()):
                monzo_account.refresh_access_token()
                account_repository.save(monzo_account)
            monzo_account.ping()
            log.info("Monzo account verified successfully.")
        except NoResultFound:
            log.warning("No valid Monzo account configured; some operations may fail.")
            monzo_account = None
        except AuthException as e:
            log.error(f"Monzo auth failed: {e}; removing config.")
            if monzo_account:
                account_repository.delete(monzo_account.type)
            monzo_account = None

        # Retrieve all valid credit accounts
        credit_accounts = account_repository.get_credit_accounts()
        log.info(f"Found {len(credit_accounts)} credit account(s).")

        if not monzo_account or not credit_accounts or not settings_repository.get("enable_sync"):
            log.info("Aborting: missing Monzo connection, no credit accounts, or sync disabled.")
            return

        for credit_account in credit_accounts:
            log.info(f"Processing {credit_account.type} start.")
            # 1) Possibly refresh tokens
            try:
                if credit_account.is_token_within_expiry_window():
                    credit_account.refresh_access_token()
                    account_repository.save(credit_account)
                credit_account.ping()
            except AuthException as e:
                log.error(f"Auth failed for {credit_account.type}, removing it. Error: {e}")
                monzo_account.send_notification(
                    f"{credit_account.type} Sync Auth Expired",
                    "Please reconnect via the portal.",
                )
                account_repository.delete(credit_account.type)
                continue

            # 2) Retrieve pot & card balances
            try:
                if not credit_account.pot_id:
                    log.info(f"{credit_account.type}: No pot allocated; skipping.")
                    continue
                account_selection = monzo_account.get_account_type(credit_account.pot_id)
                pot_balance = monzo_account.get_pot_balance(credit_account.pot_id)
                card_balance = credit_account.get_total_balance()
                prev_card = credit_account.prev_balance or 0
                # StablePot is the persistent baseline pot balance (set initially or reset on normal activity)
                log.info(f"{credit_account.type}: Live Pot Balance (PotBalance) = {pot_balance}")
                log.info(f"{credit_account.type}: Live Card Balance (CardBalance) = {card_balance}")
                log.info(f"{credit_account.type}: Previous Sync Recorded Card Balance (PrevCard) = {prev_card}")
                log.info(f"{credit_account.type}: Persistent Baseline Pot Balance - Set Initially or Reset on Normal Activity) (StablePot) = {credit_account.stable_pot_balance}")
                # Set stable baseline once if not already set
                if credit_account.stable_pot_balance is None:
                    credit_account.stable_pot_balance = pot_balance
                    log.info(f"{credit_account.type}: StablePot set to {pot_balance} as initial baseline.")
                    account_repository.save(credit_account)
                # Also, if this account is new (prev_balance == 0) set it to card_balance
                if prev_card == 0 and card_balance > 0:
                    log.info(f"{credit_account.type}: PrevCard uninitialized. Setting PrevCard to {card_balance}.")
                    credit_account.prev_balance = card_balance
                    account_repository.save(credit_account)
                    prev_card = card_balance
            except Exception as e:
                log.error(f"{credit_account.type}: Exception retrieving balances: {e}")
                continue

            now = int(time())
            cooldown_active = credit_account.cooldown_until and (now < credit_account.cooldown_until)
            cooldown_expired = credit_account.cooldown_until and (now >= credit_account.cooldown_until)

            # 3) If not in cooldown, handle normal activity
            if not cooldown_active and not cooldown_expired:
                # Use stable baseline for pot for cooldown detection
                stable_pot = credit_account.stable_pot_balance
                # (a) If pot dropped significantly below stable baseline and card balance unchanged => trigger cooldown
                if (pot_balance < stable_pot and card_balance == prev_card):
                    log.info(f"Detected unexpected pot drop for {credit_account.type} (stable baseline {stable_pot} -> current {pot_balance}). Initiating cooldown.")
                    cooldown_hours = int(settings_repository.get("deposit_cooldown_hours") or 3)
                    credit_account.cooldown_until = now + (cooldown_hours * 3600)
                    hr_cooldown = datetime.datetime.fromtimestamp(credit_account.cooldown_until).strftime("%Y-%m-%d %H:%M:%S")
                    log.info(f"{credit_account.type} cooldown set until {hr_cooldown} (epoch={credit_account.cooldown_until})")
                    credit_account.cooldown_ref_card_balance = card_balance
                    credit_account.cooldown_ref_pot_balance = pot_balance
                    account_repository.save(credit_account)
                else:
                    # (b) If card went up => deposit difference; update stable baseline on normal activity.
                    if card_balance > prev_card:
                        diff = card_balance - prev_card
                        monzo_account_balance = monzo_account.get_balance(account_selection=account_selection)
                        if monzo_account_balance < diff:
                            log.error("Insufficient Monzo funds to deposit. Disabling sync.")
                            settings_repository.save(Setting("enable_sync", "False"))
                            monzo_account.send_notification(
                                "Insufficient Funds for Sync",
                                "Please top up your Monzo account and re-enable sync.",
                                account_selection=account_selection,
                            )
                            return
                        monzo_account.add_to_pot(credit_account.pot_id, diff, account_selection=account_selection)
                        log.info(f"Deposited {diff} into pot for {credit_account.type}.")
                        # Update both prev_balance and stable baseline to the new card balance
                        credit_account.prev_balance = card_balance
                        credit_account.stable_pot_balance = pot_balance  # Reset baseline after normal deposit
                        account_repository.save(credit_account)
                    elif card_balance < prev_card:
                        diff = prev_card - card_balance
                        monzo_account.withdraw_from_pot(credit_account.pot_id, diff, account_selection=account_selection)
                        log.info(f"Withdrew {diff} from pot for {credit_account.type}.")
                        credit_account.prev_balance = card_balance
                        credit_account.stable_pot_balance = pot_balance  # Reset baseline after withdrawal
                        account_repository.save(credit_account)

            # 4) If cooldown expired => check if pot < card -> top up
            if cooldown_expired:
                hr_cooldown_expired = datetime.datetime.fromtimestamp(credit_account.cooldown_until).strftime("%Y-%m-%d %H:%M:%S")
                log.info(f"Cooldown expired for {credit_account.type}, previously set until {hr_cooldown_expired}")
                ref_card = credit_account.cooldown_ref_card_balance or card_balance
                if pot_balance < ref_card:
                    diff = ref_card - pot_balance
                    monzo_account_balance = monzo_account.get_balance(account_selection=account_selection)
                    if monzo_account_balance >= diff:
                        monzo_account.add_to_pot(credit_account.pot_id, diff, account_selection=account_selection)
                        log.info(f"Cooldown expired for {credit_account.type}, topped up {diff}.")
                    else:
                        log.warning("Cooldown expired but insufficient funds to top up pot.")
                credit_account.cooldown_until = None
                credit_account.cooldown_ref_card_balance = None
                credit_account.cooldown_ref_pot_balance = None
                account_repository.save(credit_account)

            # 5) If cooldown is active => handle partial top-ups & possible cooldown ending
            elif cooldown_active:
                # a) If card increased => deposit difference, keep cooldown
                if settings_repository.get("override_cooldown_spending") == "True":
                    if card_balance > prev_card:
                        diff = card_balance - prev_card
                        monzo_account.add_to_pot(credit_account.pot_id, diff, account_selection=account_selection)
                        log.info(f"Cooldown override deposit of {diff} for {credit_account.type}.")
                        credit_account.prev_balance = card_balance
                        account_repository.save(credit_account)

                # b) If pot == card => end cooldown
                if pot_balance == card_balance:
                    log.info(f"Cooldown ended early for {credit_account.type} because pot == card.")
                    credit_account.cooldown_until = None
                    credit_account.cooldown_ref_card_balance = None
                    credit_account.cooldown_ref_pot_balance = None
                    account_repository.save(credit_account)

            log.info(f"Processing {credit_account.type} complete.")
    log.info("All credit accounts processed.")
