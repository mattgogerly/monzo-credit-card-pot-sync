import logging
import ast
from sqlalchemy.exc import NoResultFound
from time import time

from app.domain.accounts import MonzoAccount, TrueLayerAccount
from app.errors import AuthException
from app.domain.settings import Setting
from app.extensions import db, scheduler
from app.models.account_repository import SqlAlchemyAccountRepository
from app.models.setting_repository import SqlAlchemySettingRepository

log = logging.getLogger("core")

account_repository = SqlAlchemyAccountRepository(db)
settings_repository = SqlAlchemySettingRepository(db)

def sync_balance():
    with scheduler.app.app_context():
        # Step 1: Retrieve and validate Monzo connection
        try:
            log.info("Retrieving Monzo connection")
            monzo_account: MonzoAccount = account_repository.get_monzo_account()

            log.info("Checking if Monzo access token needs refreshing")
            if (monzo_account.is_token_within_expiry_window()):
                monzo_account.refresh_access_token()
                account_repository.save(monzo_account)

            log.info("Pinging Monzo connection to verify health")
            monzo_account.ping()
            log.info("Monzo connection is healthy")
        except NoResultFound:
            log.error("No Monzo connection configured; sync will not run")
            monzo_account = None
        except AuthException:
            log.error("Monzo connection authentication failed; deleting configuration and aborting sync")
            account_repository.delete(monzo_account.type)
            monzo_account = None

        log.info("Retrieving credit card connections")
        credit_accounts: list[TrueLayerAccount] = account_repository.get_credit_accounts()
        log.info(f"Retrieved {len(credit_accounts)} credit card connection(s)")

        for credit_account in credit_accounts:
            try:
                log.info(f"Checking if {credit_account.type} access token needs refreshing")
                if (credit_account.is_token_within_expiry_window()):
                    credit_account.refresh_access_token()
                    account_repository.save(credit_account)

                log.info(f"Checking health of {credit_account.type} connection")
                credit_account.ping()
                log.info(f"{credit_account.type} connection is healthy")

            except AuthException as e:
                error_message = str(e)
                log.error(f"Failed to check health of {credit_account.type} connection; connection will be removed. Error: {error_message}")

                # Try to extract the provider's error_description from the error message.
                error_desc = ""
                try:
                    # Expecting error_message to contain something like "... missing fields: { ... }"
                    error_part = error_message.split("missing fields: ")[-1]
                    err_dict = ast.literal_eval(error_part)
                    error_desc = err_dict.get("error_description", "")
                except Exception:
                    error_desc = error_message

                # If the provider indicates unavailability (using error_description), skip notification/deletion.
                if ("currently unavailable" not in error_desc):
                    if (monzo_account is not None):
                        monzo_account.send_notification(
                            f"{credit_account.type} Pot Sync Access Expired",
                            "Reconnect the account(s) on your Monzo Credit Card Pot Sync portal to resume sync",
                        )
                    account_repository.delete(credit_account.type)
                else:
                    log.info(f"Service provider for {credit_account.type} is currently unavailable, will retry later.")
        # nothing to sync, so exit now
        if (monzo_account is None or len(credit_accounts) == 0):
            log.info(
                "Either Monzo connection is invalid, or there are no valid credit card connections; exiting sync loop"
            )
            return

        # Only initialize prev_balance on first run (e.g. if it's not already set).
        for credit_account in credit_accounts:
            if credit_account.pot_id and credit_account.get_prev_balance(credit_account.pot_id) == 0:
                live = monzo_account.get_pot_balance(credit_account.pot_id)
                # Instead of calling update_prev_balance (which persists live balance immediately),
                # simply set the in-memory value once.
                credit_account.prev_balances[credit_account.pot_id] = live
                log.info(f"Initialized prev_balance for {credit_account.type} pot {credit_account.pot_id} to {live}")

        # Step 2: Calculate balance differentials for each designated credit card pot
        pot_balance_map = {}

        for credit_account in credit_accounts:
            try:
                pot_id = credit_account.pot_id
                if (not pot_id):
                    raise NoResultFound(f"No designated credit card pot set for {credit_account.type}")

                # Determine account selection based on account type
                account_selection = monzo_account.get_account_type(pot_id)

                if (pot_id not in pot_balance_map):
                    log.info(f"Retrieving balance for credit card pot {pot_id}")
                    pot_balance = monzo_account.get_pot_balance(pot_id)
                    pot_balance_map[pot_id] = {'balance': pot_balance, 'account_selection': account_selection}
                    log.info(f"Credit card pot {pot_id} balance is £{pot_balance / 100:.2f}")
            except NoResultFound:
                log.error(
                    f"No designated credit card pot configured for {credit_account.type}; exiting sync loop"
                )
                return

            log.info(f"Retrieving balance for {credit_account.type} credit card")
            credit_balance = credit_account.get_total_balance()
            log.info(f"{credit_account.type} card balance is £{credit_balance / 100:.2f}")

            # Adjust the designated pot balance by subtracting the credit card balance
            pot_balance_map[pot_id]['balance'] -= credit_balance

        if (not settings_repository.get("enable_sync")):
            log.info("Balance sync is disabled; exiting sync loop")
            return

        # Build mapping from pot_id to credit account for withdrawal check later
        pot_to_credit_account = {}
        for credit_account in credit_accounts:
            if (credit_account.pot_id):
                pot_to_credit_account[credit_account.pot_id] = credit_account

        # Step 3: Perform necessary balance adjustments between Monzo account and each pot
        for pot_id, pot_info in pot_balance_map.items():
            pot_diff = pot_info['balance']
            account_selection = pot_info['account_selection']

            try:
                log.info(f"Retrieving Monzo account balance for {account_selection} account")
                monzo_balance = monzo_account.get_balance(account_selection=account_selection)
                log.info(f"Monzo {account_selection} account balance is £{monzo_balance / 100:.2f}")
            except AuthException:
                log.error(f"Failed to retrieve Monzo {account_selection} account balance; aborting sync loop")
                return

            log.info(f"Pot {pot_id} balance differential is £{pot_diff / 100:.2f}")

            if (pot_diff == 0):
                log.info("No balance difference; no action required")
            elif pot_diff < 0:
                # Negative differential: need to deposit funds into the pot.
                difference = abs(pot_diff)
                if monzo_balance < difference:
                    log.error("Insufficient funds in Monzo account to sync pot; disabling sync")
                    settings_repository.save(Setting("enable_sync", "False"))
                    monzo_account.send_notification(
                        "Insufficient Funds for Sync",
                        "Sync disabled due to low Monzo balance. Please top up and re-enable sync.",
                        account_selection=account_selection
                    )
                    return

                # Retrieve credit account corresponding to this pot.
                credit_account = pot_to_credit_account.get(pot_id)
                if credit_account is None:
                    log.error(f"No credit account found for pot {pot_id}. Skipping deposit.")
                    continue

                # Always compute the fresh live pot balance.
                current_pot_balance = monzo_account.get_pot_balance(pot_id)
                # Retrieve the persisted previous balance (if any)
                persisted_previous_balance = credit_account.get_prev_balance(pot_id)
                log.info(f"Persisted previous balance for {pot_id}: {persisted_previous_balance}")
                log.info(f"Current pot balance for {pot_id}: {current_pot_balance}")
                
                # Only proceed with deposit if the live balance has dropped below the persisted balance.
                if current_pot_balance < credit_balance:
                    log.info(f"No deposit required because live balance ({current_pot_balance}) is not below persisted ({persisted_previous_balance}).")
                    continue

                # Optional: apply cooldown if needed.
                try:
                    deposit_cooldown_hours = int(settings_repository.get("deposit_cooldown_hours"))
                except Exception:
                    deposit_cooldown_hours = 0
                cooldown_duration = deposit_cooldown_hours * 3600
                now = int(time())
                if credit_account.cooldown_until and now < credit_account.cooldown_until:
                    dt_str = __import__("datetime").datetime.fromtimestamp(credit_account.cooldown_until).isoformat()
                    log.info(f"Deposit postponed for {credit_account.type} due to active cooldown until {dt_str}.")
                    continue
                else:
                    credit_account.cooldown_until = now + cooldown_duration
                    dt_str = __import__("datetime").datetime.fromtimestamp(credit_account.cooldown_until).isoformat()
                    log.info(f"Cooldown initiated until {dt_str} for {credit_account.type}.")
                    continue

                # Proceed with deposit
                if monzo_balance < difference:
                    log.error("Insufficient funds in Monzo account to sync pot; disabling sync")
                    settings_repository.save(Setting("enable_sync", "False"))
                    monzo_account.send_notification(
                        "Insufficient Funds for Sync",
                        "Sync disabled due to low Monzo balance. Please top up and re-enable sync.",
                        account_selection=account_selection
                    )
                    return

                log.info(f"Depositing £{difference / 100:.2f} into credit card pot {pot_id}")
                monzo_account.add_to_pot(pot_id, difference, account_selection=account_selection)
                log.info(f"[Before Deposit] {credit_account.type} prev_balances: {credit_account.prev_balances}")
                # After depositing:
                # current_pot_balance is freshly fetched (after deposit)
                credit_account.update_prev_balance(pot_id, current_pot_balance + difference)
                log.info(f"[After Deposit] {credit_account.type} prev_balances: {credit_account.prev_balances}")
                account_repository.save(credit_account)
            else:
                # Positive differential: need to withdraw funds from the pot back to the account.
                difference = abs(pot_diff)
                credit_account = pot_to_credit_account.get(pot_id)
                if credit_account is None:
                    log.error(f"No credit account found for pot {pot_id}. Skipping withdrawal.")
                    continue
                
                log.info(f"Withdrawing £{difference / 100:.2f} from credit card pot {pot_id}")
                monzo_account.withdraw_from_pot(pot_id, difference, account_selection=account_selection)
                
                log.info(f"[Before Withdrawal] {credit_account.type} prev_balances: {credit_account.prev_balances}")
                
                # NEW: fetch the fresh live pot balance after withdrawal
                current_pot_balance = monzo_account.get_pot_balance(pot_id)
                
                # Update persisted previous balance based on the fresh balance
                credit_account.update_prev_balance(pot_id, current_pot_balance + difference)
                log.info(f"[After Withdrawal] {credit_account.type} prev_balances: {credit_account.prev_balances}")
                account_repository.save(credit_account)