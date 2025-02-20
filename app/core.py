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
                if ("The provider service is currently unavailable or experiencing technical difficulties. Please try again later." in error_message):
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
            log.info("Either Monzo connection is invalid, or there are no valid credit card connections; exiting sync loop")
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

        if (not settings_repository.get("enable_sync")):
            log.info("Balance sync is disabled; exiting sync loop")
            return

        # Build mapping from (pot_id, account.type) to credit account for further updates.
        pot_to_credit_account = {}
        for credit_account in credit_accounts:
            if (credit_account.pot_id):
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

            # For each credit account associated to this pot:
            key = f"{pot_id}_{pot_info['credit_type']}"
            credit_account = pot_to_credit_account.get(key)
            if credit_account is None:
                log.error(f"No credit account found for pot {pot_id}. Skipping adjustments.")
                continue

            # Retrieve live balances.
            live_card_balance = credit_account.get_total_balance()
            pot_balance_live = monzo_account.get_pot_balance(pot_id)
            
            # If no cooldown is active, record current balance as pre-cooldown.
            if credit_account.cooldown_until is None:
                credit_account.cooldown_start_balance = live_card_balance
            # Ensure cooldown_start_balance is set (guard against None)
            if credit_account.cooldown_start_balance is None:
                credit_account.cooldown_start_balance = live_card_balance

            # Now compute delta safely.
            delta = live_card_balance - credit_account.cooldown_start_balance

            if delta > 0:
                # Card balance increased => deposit the difference.
                if monzo_balance < delta:
                    log.error("Insufficient funds in Monzo account to deposit; disabling sync")
                    settings_repository.save(Setting("enable_sync", "False"))
                    monzo_account.send_notification(
                        "Insufficient Funds for Sync",
                        "Sync disabled due to low Monzo balance. Please top up and re‑enable sync.",
                        account_selection=account_selection
                    )
                    return
                log.info(f"Card increased by {delta}; depositing into pot {pot_id}.")
                selection = monzo_account.get_account_type(pot_id)
                monzo_account.add_to_pot(pot_id, delta, account_selection=selection)
                new_balance = monzo_account.get_pot_balance(pot_id)
                account_repository.update_credit_account_fields(credit_account.type, pot_id, new_balance, None, credit_account.cooldown_start_balance, None)
                credit_account.prev_balance = new_balance
                # After deposit, clear cooldown by setting its expiration to now, so future runs can update.
                credit_account.cooldown_until = int(time())
                log.info("Deposit completed; cooldown cleared.")
            elif delta < 0:
                # Card balance decreased further than pre-cooldown => withdraw the excess.
                withdraw_amount = abs(delta)
                log.info(f"Card decreased by {withdraw_amount}; withdrawing from pot {pot_id}.")
                monzo_account.withdraw_from_pot(pot_id, withdraw_amount, account_selection=account_selection)
                new_balance = monzo_account.get_pot_balance(pot_id)
                account_repository.update_credit_account_fields(credit_account.type, pot_id, new_balance, None, credit_account.cooldown_start_balance, None)
                credit_account.prev_balance = new_balance
            else:
                # delta == 0: accounts balanced, clear cooldown.
                log.info(f"Card and pre-cooldown balance equal for {credit_account.type}; no action taken. Clearing cooldown.")
                account_repository.update_credit_account_fields(credit_account.type, pot_id, pot_balance_live, int(time()), None, None)
                credit_account.cooldown_until = int(time())
                credit_account.cooldown_start_balance = None

        # Final deposit re-check loop: if cooldown has expired.
        for credit_account in credit_accounts:
            if credit_account.pot_id and credit_account.cooldown_until:
                if int(time()) < credit_account.cooldown_until:
                    human_readable = datetime.datetime.fromtimestamp(credit_account.cooldown_until).strftime("%Y-%m-%d %H:%M:%S")
                    log.info(f"Cooldown still active for {credit_account.type} pot {credit_account.pot_id} until {human_readable}. Skipping deposit re-check.")
                    continue
                pre_deposit = credit_account.get_prev_balance(credit_account.pot_id)
                current_balance = monzo_account.get_pot_balance(credit_account.pot_id)
                # Use the stored cooldown_start_balance as baseline if set.
                baseline = credit_account.cooldown_start_balance if credit_account.cooldown_start_balance is not None else pre_deposit
                drop = baseline - current_balance
                if drop > 0:
                    try:
                        deposit_cooldown_hours = int(settings_repository.get("deposit_cooldown_hours"))
                    except Exception:
                        deposit_cooldown_hours = 0
                    cooldown_duration = deposit_cooldown_hours * 3600
                    log.info(f"Post-cooldown deposit: depositing pending drop of {drop} into pot {credit_account.pot_id}.")
                    selection = monzo_account.get_account_type(credit_account.pot_id)
                    monzo_account.add_to_pot(credit_account.pot_id, drop, account_selection=selection)
                    new_balance = monzo_account.get_pot_balance(credit_account.pot_id)
                    account_repository.update_credit_account_fields(
                        credit_account.type, credit_account.pot_id, new_balance, None, None, None
                    )
                    credit_account.prev_balance = new_balance
                else:
                    log.info(f"No pending drop persists for {credit_account.type} pot {credit_account.pot_id} after cooldown. Leaving deposit unexecuted.")

        # Final loop: update persisted baseline; if the cooldown period has expired and no deposit is needed,
        # then clear the cooldown flag.
        current_time = int(time())
        for credit_account in credit_accounts:
            if (credit_account.pot_id):
                live = credit_account.get_total_balance()
                prev = credit_account.get_prev_balance(credit_account.pot_id)
                if (credit_account.cooldown_until):
                    if (current_time < credit_account.cooldown_until):
                        log.info(
                            f"Cooldown still active for {credit_account.type} pot {credit_account.pot_id} "
                            f"(cooldown until {datetime.datetime.fromtimestamp(credit_account.cooldown_until).strftime('%Y-%m-%d %H:%M:%S')}). "
                            "Baseline not updated."
                        )
                        continue
                    log.info(f"Cooldown expired for {credit_account.type} pot {credit_account.pot_id}; clearing cooldown.")
                    account_repository.update_credit_account_fields(credit_account.type, credit_account.pot_id, prev, None)
                    credit_account.cooldown_until = None
                if (live > prev):
                    account_repository.update_credit_account_fields(credit_account.type, credit_account.pot_id, live)
                    credit_account.prev_balance = live
                    log.info(f"Updated baseline for {credit_account.type} pot {credit_account.pot_id} to {live}.")
                else:
                    log.info(f"Persisted baseline for {credit_account.type} pot {credit_account.pot_id} remains unchanged (prev: {prev}, live: {live})")

        # Final deposit re-check loop: only process if cooldown has expired.
        for credit_account in credit_accounts:
            if (credit_account.pot_id and credit_account.cooldown_until):
                if (current_time < credit_account.cooldown_until):
                    human_readable = datetime.datetime.fromtimestamp(credit_account.cooldown_until).strftime("%Y-%m-%d %H:%M:%:%S")
                    log.info(f"Cooldown still active for {credit_account.type} pot {credit_account.pot_id} (cooldown until {human_readable}). Skipping deposit re-check.")
                    continue
                pre_deposit = credit_account.get_prev_balance(credit_account.pot_id)
                current_balance = monzo_account.get_pot_balance(credit_account.pot_id)
                # Use the stored cooldown_start_balance as the baseline.
                baseline = credit_account.cooldown_start_balance if credit_account.cooldown_start_balance is not None else pre_deposit
                drop = baseline - current_balance
                if (drop > 0):
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
                    account_repository.update_credit_account_fields(
                        credit_account.type, credit_account.pot_id, new_balance
                    )
                    credit_account.prev_balance = new_balance
                else:
                    log.info(f"No drop persists for {credit_account.type} pot {credit_account.pot_id} after cooldown. Leaving deposit unexecuted.")
                # Optionally, clear cooldown if handled.
                # credit_account.cooldown_until = None
                # account_repository.update_credit_account_fields(credit_account.type, credit_account.pot_id, current_balance)

        # Assume monzo_account and credit_accounts have been validated.
        if (monzo_account is None or len(credit_accounts) == 0):
            log.info("Either Monzo connection is invalid, or there are no valid credit card connections; exiting sync loop")
            return

        # Build map to retrieve each credit account by key (pot_id + type)
        pot_to_credit_account = {}
        for credit_account in credit_accounts:
            if credit_account.pot_id:
                key = f"{credit_account.pot_id}_{credit_account.type}"
                pot_to_credit_account[key] = credit_account

        now = int(time())
        try:
            deposit_cooldown_hours = int(settings_repository.get("deposit_cooldown_hours"))
        except Exception:
            deposit_cooldown_hours = 0
        cooldown_duration = deposit_cooldown_hours * 3600

        # Process each credit account one at a time for clarity in logging.
        for credit_account in credit_accounts:
            log.info(f"--- Processing account: {credit_account.type} (pot: {credit_account.pot_id}) ---")
            
            # Refresh persisted data for this account.
            refreshed = account_repository.get(credit_account.type)
            credit_account.cooldown_until = refreshed.cooldown_until
            credit_account.prev_balance = refreshed.prev_balance
            
            # Log baseline details.
            log.info(f"Baseline for {credit_account.type} (prev_balance: {credit_account.prev_balance}, cooldown_until: {credit_account.cooldown_until}, cooldown_start_balance: {credit_account.cooldown_start_balance})")
            
            # For this account, determine pot and card balance.
            pot_id = credit_account.pot_id
            try:
                pot_balance = monzo_account.get_pot_balance(pot_id)
            except Exception as e:
                log.error(f"Error retrieving pot balance for {pot_id}: {e}")
                continue
            
            card_balance = credit_account.get_total_balance()
            log.info(f"Account {credit_account.type}: card balance = £{card_balance/100:.2f}, pot balance = £{pot_balance/100:.2f}")

            # If card balance > pot balance, run deposit flow.
            if card_balance > pot_balance:
                log.info(f"Running deposit flow for {credit_account.type}")
                # Use cooldown_start_balance if set, otherwise use prev_balance
                baseline = credit_account.cooldown_start_balance if credit_account.cooldown_start_balance is not None else credit_account.prev_balance
                log.info(f"Deposit baseline for {credit_account.type} is {baseline}")
                deposit_amount = card_balance - baseline
                log.info(f"Deposit amount calculated: {deposit_amount}")
                if deposit_amount > 0:
                    # Check if we are within cooldown before proceeding:
                    now = int(time())
                    if credit_account.cooldown_until and now < credit_account.cooldown_until:
                        human_readable = datetime.datetime.fromtimestamp(credit_account.cooldown_until).strftime("%Y-%m-%d %H:%M:%S")
                        log.info(f"Deposit check aborted because cooldown active for {credit_account.type} until {human_readable}.")
                    else:
                        if credit_account.get_total_balance() > credit_account.prev_balance:
                            # Proceed with deposit
                            try:
                                monzo_balance = monzo_account.get_balance(account_selection=monzo_account.get_account_type(pot_id))
                            except AuthException:
                                log.error("Cannot retrieve Monzo balance; aborting deposit.")
                                continue
                            if monzo_balance < deposit_amount:
                                log.error("Insufficient funds in Monzo account to deposit; disabling sync")
                                settings_repository.save(Setting("enable_sync", "False"))
                                monzo_account.send_notification(
                                    "Insufficient Funds for Sync",
                                    "Sync disabled due to low Monzo balance. Please top up and re‑enable sync.",
                                    account_selection=monzo_account.get_account_type(pot_id)
                                )
                                continue
                            log.info(f"Depositing £{deposit_amount/100:.2f} into pot {pot_id} for {credit_account.type} (card increased from baseline {baseline}).")
                            monzo_account.add_to_pot(pot_id, deposit_amount, account_selection=monzo_account.get_account_type(pot_id))
                            new_balance = monzo_account.get_pot_balance(pot_id)
                            account_repository.update_credit_account_fields(credit_account.type, pot_id, new_balance, None, None, None)
                            credit_account.prev_balance = new_balance
                        else:
                            # No card increase: start or extend cooldown.
                            now = int(time())
                            try:
                                deposit_cooldown_hours = int(settings_repository.get("deposit_cooldown_hours"))
                            except Exception:
                                deposit_cooldown_hours = 0
                            cooldown_duration = deposit_cooldown_hours * 3600
                            new_cooldown = now + cooldown_duration if cooldown_duration > 0 else None
                            # Set cooldown_start_balance if not already set.
                            if credit_account.cooldown_until is None:
                                credit_account.cooldown_start_balance = credit_account.get_total_balance()
                            log.info(f"No card increase for {credit_account.type}; triggering cooldown until {datetime.datetime.fromtimestamp(new_cooldown).strftime('%Y-%m-%d %H:%M:%S')} and saving pending drop of {deposit_amount}.")
                            updated_account = account_repository.update_credit_account_fields(
                                credit_account.type, pot_id, pot_balance, new_cooldown, credit_account.cooldown_start_balance, deposit_amount
                            )
                            credit_account.cooldown_until = updated_account.cooldown_until
                            credit_account.pending_drop = deposit_amount
                else:
                    log.info(f"No deposit required for {credit_account.type} (deposit_amount ≤ 0).")
            
            # If pot balance > card balance, run withdrawal flow.
            elif pot_balance > card_balance:
                withdraw_amount = pot_balance - card_balance
                log.info(f"Running withdrawal flow for {credit_account.type}: withdrawing £{withdraw_amount/100:.2f} from pot {pot_id}.")
                monzo_account.withdraw_from_pot(pot_id, withdraw_amount, account_selection=monzo_account.get_account_type(pot_id))
                new_balance = monzo_account.get_pot_balance(pot_id)
                account_repository.update_credit_account_fields(credit_account.type, pot_id, new_balance, None, None)
                credit_account.prev_balance = new_balance
            
            # If card balance equals pot balance, clear any expired cooldown.
            else:
                now = int(time())
                if credit_account.cooldown_until and now >= credit_account.cooldown_until:
                    log.info(f"Cooldown expired for {credit_account.type}; clearing cooldown for pot {pot_id}.")
                    account_repository.update_credit_account_fields(credit_account.type, pot_id, pot_balance, None, None)
                    credit_account.cooldown_until = None
                    credit_account.cooldown_start_balance = None
                else:
                    log.info(f"No balance difference for {credit_account.type}; no action taken.")
            
            log.info(f"--- Finished processing account: {credit_account.type} ---")

        # Final deposit re‑check loop: ensure any residual pending drop is addressed after cooldown expires.
        log.info("Starting final re‑check loop for residual pending drops.")
        for credit_account in credit_accounts:
            if credit_account.pot_id and credit_account.cooldown_until:
                current_time = int(time())
                if current_time < credit_account.cooldown_until:
                    human_readable = datetime.datetime.fromtimestamp(credit_account.cooldown_until).strftime("%Y-%m-%d %H:%M:%S")
                    log.info(f"Account {credit_account.type} cooldown still active until {human_readable}; skipping re‑check.")
                    continue

                # Use the stored cooldown_start_balance as the baseline.
                baseline = credit_account.cooldown_start_balance if credit_account.cooldown_start_balance is not None else credit_account.get_prev_balance(credit_account.pot_id)
                current_pot_balance = monzo_account.get_pot_balance(credit_account.pot_id)
                pending_drop = baseline - current_pot_balance
                log.info(f"Re‑check for {credit_account.type}: baseline {baseline}, current pot balance {current_pot_balance}, pending drop {pending_drop}.")

                if pending_drop > 0:
                    log.info(f"Residual pending drop detected for {credit_account.type} (pending drop: {pending_drop}). Executing deposit.")
                    selection = monzo_account.get_account_type(credit_account.pot_id)
                    monzo_account.add_to_pot(credit_account.pot_id, pending_drop, account_selection=selection)
                    new_balance = monzo_account.get_pot_balance(credit_account.pot_id)
                    account_repository.update_credit_account_fields(credit_account.type, credit_account.pot_id, new_balance, None, None, None)
                    credit_account.prev_balance = new_balance
                    log.info(f"Re‑check deposit complete for {credit_account.type}; new pot balance: {new_balance}.")
                else:
                    log.info(f"No residual pending drop for {credit_account.type}; no deposit re‑check action taken.")
        log.info("Final re‑check loop complete.")