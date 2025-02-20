import logging
import ast
from sqlalchemy.exc import NoResultFound
from time import time
import datetime  # Add import if not already present

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
            if monzo_account.is_token_within_expiry_window():
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
                if credit_account.is_token_within_expiry_window():
                    credit_account.refresh_access_token()
                    account_repository.save(credit_account)
                log.info(f"Checking health of {credit_account.type} connection")
                credit_account.ping()
                log.info(f"{credit_account.type} connection is healthy")
            except AuthException as e:
                error_message = str(e)
                if "The provider service is currently unavailable or experiencing technical difficulties. Please try again later." in error_message:
                    log.error(f"{credit_account.type} token refresh failed due to provider issues: {error_message}. Exiting sync to try again later.")
                    return  # Exit the sync cycle gracefully
                else:
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
                if "currently unavailable" not in error_desc:
                    if monzo_account is not None:
                        monzo_account.send_notification(
                            f"{credit_account.type} Pot Sync Access Expired",
                            "Reconnect the account(s) on your Monzo Credit Card Pot Sync portal to resume sync",
                        )
                    account_repository.delete(credit_account.type)
                else:
                    log.info(f"Service provider for {credit_account.type} is currently unavailable, will retry later.")

        # nothing to sync, so exit now
        if monzo_account is None or len(credit_accounts) == 0:
            log.info("Either Monzo connection is invalid, or there are no valid credit card connections; exiting sync loop")
            return

        # Step 2: Calculate balance differentials for each designated credit card pot
        pot_balance_map = {}

        for credit_account in credit_accounts:
            try:
                pot_id = credit_account.pot_id
                if not pot_id:
                    raise NoResultFound(f"No designated credit card pot set for {credit_account.type}")

                # Determine account selection based on account type
                account_selection = monzo_account.get_account_type(pot_id)

                if pot_id not in pot_balance_map:
                    log.info(f"Retrieving balance for credit card pot {pot_id}")
                    pot_balance = monzo_account.get_pot_balance(pot_id)
                    # Include the credit account type for later key construction.
                    pot_balance_map[pot_id] = {
                        'balance': pot_balance,
                        'account_selection': account_selection,
                        'credit_type': credit_account.type
                    }
                    log.info(f"Credit card pot {pot_id} balance is £{pot_balance / 100:.2f}")
            except NoResultFound:
                log.error(f"No designated credit card pot configured for {credit_account.type}; exiting sync loop")
                return

            log.info(f"Retrieving balance for {credit_account.type} credit card")
            credit_balance = credit_account.get_total_balance()
            log.info(f"{credit_account.type} card balance is £{credit_balance / 100:.2f}")

            # Adjust the designated pot balance by subtracting the credit card balance
            pot_balance_map[pot_id]['balance'] -= credit_balance

        if not settings_repository.get("enable_sync"):
            log.info("Balance sync is disabled; exiting sync loop")
            return

        # Build mapping from (pot_id, account.type) to credit account for further updates.
        pot_to_credit_account = {}
        for credit_account in credit_accounts:
            if credit_account.pot_id:
                key = f"{credit_account.pot_id}_{credit_account.type}"
                pot_to_credit_account[key] = credit_account

        # After calculating pot balance differentials (Step 2) and before performing adjustments:
        # Refresh credit account objects with persisted values (e.g. active cooldown)
        for i, credit_account in enumerate(credit_accounts):
            refreshed = account_repository.get(credit_account.type)
            credit_accounts[i].cooldown_until = refreshed.cooldown_until
            credit_accounts[i].prev_balance = refreshed.prev_balance
        log.info("Refreshed credit account data including cooldown values.")

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

            if pot_diff == 0:
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

                key = f"{pot_id}_{pot_info['credit_type']}"
                credit_account = pot_to_credit_account.get(key)
                if credit_account is None:
                    log.error(f"No credit account found for pot {pot_id}. Skipping deposit.")
                    continue

                # Get current pot balance
                pre_deposit_balance = monzo_account.get_pot_balance(pot_id)
                log.info(f"Pre-deposit balance for pot {pot_id} is {pre_deposit_balance}")

                now = int(time())
                deposit_executed = False
                # FIRST: check if a cooldown exists.
                if credit_account.cooldown_until is not None:
                    if now < credit_account.cooldown_until:
                        human_readable = datetime.datetime.fromtimestamp(credit_account.cooldown_until).strftime("%Y-%m-%d %H:%M:%S")
                        log.info(f"Cooldown active for {credit_account.type} pot {pot_id} until {human_readable}. Skipping deposit.")
                        continue
                    else:
                        # Cooldown expired: execute deposit only once.
                        log.info(f"Cooldown expired for {credit_account.type} pot {pot_id}. Executing deposit now.")
                        desired_balance = credit_account.get_total_balance()
                        deposit_amount = desired_balance - pre_deposit_balance
                        if deposit_amount > 0:
                            selection = monzo_account.get_account_type(pot_id)
                            monzo_account.add_to_pot(pot_id, deposit_amount, account_selection=selection)
                            new_balance = monzo_account.get_pot_balance(pot_id)
                            account_repository.update_credit_account_fields(credit_account.type, pot_id, new_balance, None)
                            credit_account.prev_balance = new_balance
                            credit_account.cooldown_until = None
                            deposit_executed = True
                            log.info(f"Post-cooldown deposit executed for {credit_account.type} pot {pot_id}; deposited £{deposit_amount/100:.2f}. New balance: {new_balance}.")
                        else:
                            log.info("No drop remains after cooldown; deposit not needed.")
                        if deposit_executed:
                            continue
                # Only if no deposit was executed, check for deposit requirement and set a new cooldown.
                if not deposit_executed:
                    log.info("No active cooldown. Checking for deposit requirement.")
                    desired_balance = credit_account.get_total_balance()
                    drop = desired_balance - pre_deposit_balance
                    log.info(f"Calculated drop based on desired balance {desired_balance} and pot balance {pre_deposit_balance} is {drop}.")
                    if drop > 0:
                        try:
                            deposit_cooldown_hours = int(settings_repository.get("deposit_cooldown_hours"))
                        except Exception:
                            deposit_cooldown_hours = 0
                        cooldown_duration = deposit_cooldown_hours * 3600
                        log.info(f"Calculated cooldown duration: {cooldown_duration} seconds.")
                        new_cooldown = now + cooldown_duration if cooldown_duration > 0 else None
                        log.info(f"Drop of {drop} detected. Setting cooldown until {datetime.datetime.fromtimestamp(new_cooldown).strftime('%Y-%m-%d %H:%M:%S') if new_cooldown else 'None'} for pot {pot_id}. Deposit will execute after cooldown if drop persists.")
                        updated_account = account_repository.update_credit_account_fields(
                            credit_account.type, pot_id, pre_deposit_balance, new_cooldown
                        )
                        credit_account.cooldown_until = updated_account.cooldown_until
                    else:
                        log.info("Calculated drop is not positive. No cooldown or deposit triggered.")
            else:
                # For positive differential (withdrawal)
                difference = abs(pot_diff)
                key = f"{pot_id}_{pot_info['credit_type']}"
                credit_account = pot_to_credit_account.get(key)
                if credit_account is None:
                    log.error(f"No credit account found for pot {pot_id}. Skipping withdrawal.")
                    continue
                log.info(f"Withdrawing £{difference / 100:.2f} from credit card pot {pot_id}")
                monzo_account.withdraw_from_pot(pot_id, difference, account_selection=account_selection)

        # Final loop: update persisted baseline; if the cooldown period has expired and no deposit is needed,
        # then clear the cooldown flag.
        current_time = int(time())
        for credit_account in credit_accounts:
            if credit_account.pot_id:
                live = credit_account.get_total_balance()
                prev = credit_account.get_prev_balance(credit_account.pot_id)
                if credit_account.cooldown_until:
                    if current_time < credit_account.cooldown_until:
                        log.info(
                            f"Cooldown still active for {credit_account.type} pot {credit_account.pot_id} "
                            f"(cooldown until {datetime.datetime.fromtimestamp(credit_account.cooldown_until).strftime('%Y-%m-%d %H:%M:%S')}). "
                            "Baseline not updated."
                        )
                        continue
                    log.info(f"Cooldown expired for {credit_account.type} pot {credit_account.pot_id}; clearing cooldown.")
                    account_repository.update_credit_account_fields(credit_account.type, credit_account.pot_id, prev, None)
                    credit_account.cooldown_until = None
                if live > prev:
                    account_repository.update_credit_account_fields(credit_account.type, credit_account.pot_id, live)
                    credit_account.prev_balance = live
                    log.info(f"Updated baseline for {credit_account.type} pot {credit_account.pot_id} to {live}.")
                else:
                    log.info(f"Persisted baseline for {credit_account.type} pot {credit_account.pot_id} remains unchanged (prev: {prev}, live: {live})")

        # Final deposit re-check loop: only run if cooldown has expired.
        for credit_account in credit_accounts:
            if credit_account.pot_id and credit_account.cooldown_until and credit_account.cooldown_until > 0:
                if current_time < credit_account.cooldown_until:
                    human_readable = datetime.datetime.fromtimestamp(credit_account.cooldown_until).strftime("%Y-%m-%d %H:%M:%S")
                    log.info(f"Cooldown still active for {credit_account.type} pot {credit_account.pot_id} (cooldown until {human_readable}). Skipping deposit re-check.")
                    continue
                pre_deposit = credit_account.get_prev_balance(credit_account.pot_id)
                current_balance = monzo_account.get_pot_balance(credit_account.pot_id)
                drop = pre_deposit - current_balance
                if drop > 0:
                    try:
                        deposit_cooldown_hours = int(settings_repository.get("deposit_cooldown_hours"))
                    except Exception:
                        deposit_cooldown_hours = 0
                    cooldown_duration = deposit_cooldown_hours * 3600
                    log.info(f"Calculated cooldown duration: {cooldown_duration} seconds.")
                    selection = monzo_account.get_account_type(credit_account.pot_id)
                    monzo_account.add_to_pot(credit_account.pot_id, drop, account_selection=selection)
                    new_balance = monzo_account.get_pot_balance(credit_account.pot_id)
                    log.info(f"Post-cooldown deposit executed for {credit_account.type} pot {credit_account.pot_id}; deposited {drop/100:.2f}. New balance: {new_balance}.")
                    account_repository.update_credit_account_fields(credit_account.type, credit_account.pot_id, new_balance)
                    credit_account.prev_balance = new_balance
                else:
                    log.info(f"No drop persists for {credit_account.type} pot {credit_account.pot_id} after cooldown. Leaving deposit unexecuted.")
                # Optionally, clear cooldown if drop has been handled:
                # credit_account.cooldown_until = None
                # account_repository.update_credit_account_fields(credit_account.type, credit_account.pot_id, current_balance)