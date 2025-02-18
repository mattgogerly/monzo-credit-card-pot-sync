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

        # Build mapping from pot_id to credit account for further updates.
        pot_to_credit_account = {}
        for credit_account in credit_accounts:
            if credit_account.pot_id and credit_account.pot_id not in pot_to_credit_account:
                pot_to_credit_account[credit_account.pot_id] = credit_account

        # Step 3: Perform necessary balance adjustments
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

                credit_account = pot_to_credit_account.get(pot_id)
                if credit_account is None:
                    log.error(f"No credit account found for pot {pot_id}. Skipping deposit.")
                    continue

                log.info(f"Applying deposit for pot {pot_id} using credit account {credit_account.type}")

                now = int(time())
                try:
                    # Removed unused assignment: deposit_cooldown_hours = int(settings_repository.get("deposit_cooldown_hours"))
                    int(settings_repository.get("deposit_cooldown_hours"))
                except Exception:
                    pass
                # Re-fetch fresh account record to check if a cooldown is still active
                fresh_account = account_repository.get(credit_account.type)
                if fresh_account.cooldown_until and now < fresh_account.cooldown_until:
                    dt_str = __import__("datetime").datetime.fromtimestamp(fresh_account.cooldown_until).isoformat()
                    log.info(f"Deposit postponed for {fresh_account.type} due to active cooldown until {dt_str}.")
                    continue
                # Do NOT reissue a new cooldown here; allow deposit to proceed when no active cooldown
                log.info(f"Depositing £{difference / 100:.2f} into credit card pot {pot_id}")
                monzo_account.add_to_pot(pot_id, difference, account_selection=account_selection)
                current_pot_balance = monzo_account.get_pot_balance(pot_id)
                # Update only the persisted baseline balance; clear cooldown by setting it to None (or leave unchanged)
                account_repository.update_credit_account_fields(
                    credit_account.type, pot_id, current_pot_balance, None
                )
                log.info(f"[After Deposit] Updated persisted prev_balance for {credit_account.type} pot {pot_id} to {current_pot_balance}")

            else:
                # For positive differential (withdrawal)
                difference = abs(pot_diff)
                credit_account = pot_to_credit_account.get(pot_id)
                if credit_account is None:
                    log.error(f"No credit account found for pot {pot_id}. Skipping withdrawal.")
                    continue

                log.info(f"Withdrawing £{difference / 100:.2f} from credit card pot {pot_id}")
                monzo_account.withdraw_from_pot(pot_id, difference, account_selection=account_selection)
        
        # At the end of the sync cycle, update the persisted baseline for each credit account.
        for credit_account in credit_accounts:
            if credit_account.pot_id:
                live = monzo_account.get_pot_balance(credit_account.pot_id)
                account_repository.update_credit_account_fields(credit_account.type, credit_account.pot_id, live)
                log.info(f"Updated persisted previous balance for {credit_account.type} pot {credit_account.pot_id} to {live}")