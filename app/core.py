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

            # Retrieve live card balance and live pot balance.
            live_card_balance = credit_account.get_total_balance()
            current_pot = monzo_account.get_pot_balance(credit_account.pot_id)
            # Ensure cooldown_start_balance is set: if None, initialize it with live_card_balance.
            if credit_account.cooldown_start_balance is None:
                credit_account.cooldown_start_balance = live_card_balance
            baseline = credit_account.cooldown_start_balance
            log.info(f"Live pot balance for pot {pot_id}: {current_pot} pence")
            drop = baseline - current_pot
            log.info(f"Computed drop for {credit_account.type} (baseline {baseline} - current pot {current_pot}): {drop} pence")

            # Retrieve deposit cooldown hours setting from settings repository, defaulting to 3 if not found.
            deposit_cooldown_hours_value = settings_repository.get("deposit_cooldown_hours")
            try:
                deposit_cooldown_hours = int(deposit_cooldown_hours_value) if deposit_cooldown_hours_value is not None else 3
            except Exception as e:
                log.error(f"Error parsing deposit_cooldown_hours setting: {e}. Defaulting to 3.")
                deposit_cooldown_hours = 3

            # Use the stored baseline (cooldown_start_balance) as the reference for the credit card's balance.
            baseline = credit_account.cooldown_start_balance

            now = int(time())
            
            # Step 1: Check if cooldown has expired and if a top-up is needed
            if credit_account.cooldown_until is not None and now >= credit_account.cooldown_until:
                if current_pot < credit_account.cooldown_start_balance:
                    log.info(f"Cooldown expired, pot balance is still low for {credit_account.type} pot {credit_account.pot_id}. Topping up balance.")
                    cooldown_expired_top_up_diff = credit_account.cooldown_start_balance - current_pot
                    
                    # Call add_to_pot to restore balance
                    selection = monzo_account.get_account_type(pot_id)
                    monzo_account.add_to_pot(credit_account.pot_id, cooldown_expired_top_up_diff, account_selection=selection)
            
                    # Clear cooldown to allow normal operations after top-up
                    credit_account.cooldown_until = None  
                    credit_account.cooldown_start_balance = live_card_balance  # Reset baseline to new balance
            
                else:
                    log.info("Cooldown expired, but pot balance is fine. Updating baseline.")
                    credit_account.cooldown_start_balance = live_card_balance  # Reset to new safe baseline
            
                account_repository.save(credit_account)
                # Stop further cooldown logic to avoid immediate retrigger
                return
            
            # Step 2: Only trigger cooldown if it's NOT in a "post-expiry" state
            if credit_account.cooldown_until is None:  
                log.debug("Cooldown recently cleared, waiting for top-up to take effect before setting new cooldown.")
            else:
                if current_pot < credit_account.cooldown_start_balance and live_card_balance == credit_account.cooldown_start_balance:
                    if now < credit_account.cooldown_until:
                        log.info(f"Cooldown already active until {datetime.datetime.fromtimestamp(credit_account.cooldown_until)}. Skipping new cooldown.")
                    else:
                        # If no active cooldown, set one
                        cooldown_seconds = deposit_cooldown_hours * 3600
                        credit_account.cooldown_until = now + cooldown_seconds
                        account_repository.save(credit_account)
                        log.info(f"New cooldown set until {datetime.datetime.fromtimestamp(credit_account.cooldown_until)}")
            
            # Compare live card balance to our fixed pre-cooldown baseline.
            baseline = credit_account.cooldown_start_balance
            delta = live_card_balance - baseline

            # Compare pot balance to live card balance
            pot_delta = current_pot - live_card_balance

            if delta > 0:
                # Card balance increased (new spending) → deposit the extra funds.
                if monzo_balance < delta:
                    log.error("Insufficient funds in Monzo account to deposit; disabling sync")
                    settings_repository.save(Setting("enable_sync", "False"))
                    monzo_account.send_notification(
                        "Insufficient Funds for Sync",
                        "Sync disabled due to low Monzo balance. Please top up and re‑enable sync.",
                        account_selection=account_selection)
                    return
                log.info(f"Card increased by {delta}; depositing into pot {pot_id}.")
                selection = monzo_account.get_account_type(pot_id)
                monzo_account.add_to_pot(pot_id, delta, account_selection=selection)
                # Instead of updating prev_balance with the pot balance, update it with the live card balance.
                new_cc = live_card_balance
                account_repository.update_credit_account_fields(
                    credit_account.type, pot_id, new_cc, None, baseline, None)
                credit_account.prev_balance = new_cc
                log.info("Deposit completed; if a cooldown is set, it remains active until full period elapses.")
            elif delta < 0:
                # Card balance decreased (payment received) → withdraw the difference.
                withdraw_amount = abs(delta)
                log.info(f"Card decreased by {withdraw_amount}; withdrawing from pot {pot_id}.")
                monzo_account.withdraw_from_pot(pot_id, withdraw_amount, account_selection=account_selection)
                new_cc = live_card_balance  # use live card balance here as well
                account_repository.update_credit_account_fields(
                    credit_account.type, pot_id, new_cc, None, baseline, None)
                credit_account.prev_balance = new_cc
                log.info("Withdrawal completed; if a cooldown is set, it remains active until full period elapses.")
            # We always want to withdraw from our pot if its balance is larger than our total card balance
            elif pot_delta > 0:
                withdraw_amount = abs(pot_delta)
                log.info(f"Card balance decreased by {withdraw_amount}; withdrawing from pot {pot_id}.")
                monzo_account.withdraw_from_pot(pot_id, withdraw_amount, account_selection=account_selection)
                new_cc = live_card_balance  # use live card balance here as well
                account_repository.update_credit_account_fields(
                    credit_account.type, pot_id, new_cc, None, baseline, None)
                credit_account.prev_balance = new_cc
                log.info("Withdrawal completed; cooldown remains active until full period elapses.")
            else:
                log.info(f"Card and baseline balance equal for {credit_account.type}; no action taken. Maintaining cooldown until full period expires.")

        # Final deposit re‑check loop: if cooldown has expired.
        for credit_account in credit_accounts:
            if credit_account.pot_id and credit_account.cooldown_until:
                # Always skip final deposit if cooldown_start_balance is still set (i.e. cooldown active)
                now = int(time())
                if now < credit_account.cooldown_until:
                    human_readable = datetime.datetime.fromtimestamp(credit_account.cooldown_until).strftime("%Y-%m-%d %H:%M:%S")
                    log.info(f"Cooldown still active for {credit_account.type} pot {credit_account.pot_id} until {human_readable}. Skipping deposit re‑check.")
                    continue
                pre_deposit = credit_account.get_prev_balance(credit_account.pot_id)
                current_balance = monzo_account.get_pot_balance(credit_account.pot_id)
                baseline = pre_deposit  # Use persisted baseline when no active cooldown
                drop = baseline - current_balance
                if drop > 0:
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

        # Final loop: update persisted baseline; if the cooldown period has expired and no
        # new confirmed spending or payment is detected, do not update prev_balance.
        current_time = int(time())
        for credit_account in credit_accounts:
            if credit_account.pot_id:
                live = credit_account.get_total_balance()
                prev = credit_account.get_prev_balance(credit_account.pot_id)
                # Only update baseline if confirmed change occurred (live > prev or live < prev)
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
                # Only update baseline when there is a confirmed change (i.e. spending or payments)
                if live != prev:
                    log.info(f"Updating baseline for {credit_account.type} pot {credit_account.pot_id} from {prev} to {live} due to confirmed change.")
                    account_repository.update_credit_account_fields(credit_account.type, credit_account.pot_id, live)
                    credit_account.prev_balance = live
                else:
                    log.info(f"Persisted baseline for {credit_account.type} pot {credit_account.pot_id} remains unchanged (prev: {prev}, live: {live}).")

        # Unified final loop (remove old final loops and replace them with the following)
        for credit_account in credit_accounts:
            if not credit_account.pot_id:
                continue

            now = int(time())
            refreshed = account_repository.get(credit_account.type)
            prev_cc = refreshed.prev_balance
            cooldown_until = refreshed.cooldown_until

            # Determine pending_base from cooldown_start_balance if set, otherwise use prev_cc
            pending_base = refreshed.cooldown_start_balance if refreshed.cooldown_start_balance is not None else prev_cc

            current_cc = credit_account.get_total_balance()
            current_pot = monzo_account.get_pot_balance(credit_account.pot_id)
            log.info(f"{credit_account.type}: current CC={current_cc}, pot={current_pot}, prev_cc={prev_cc}, pending_base={pending_base}")

            # Check if cooldown is active:
            if (cooldown_until is not None and now < cooldown_until):
                # If override is enabled, check for new spending diff
                if settings_repository.get("override_cooldown_spending") == "True":
                    diff = current_cc - prev_cc
                    if diff > 0:
                        log.info(f"Override active for {credit_account.type}: new spending of {diff} detected during cooldown.")
                        selection = monzo_account.get_account_type(credit_account.pot_id)
                        monzo_account.add_to_pot(credit_account.pot_id, diff, account_selection=selection)
                        new_balance = monzo_account.get_pot_balance(credit_account.pot_id)
                        account_repository.update_credit_account_fields(
                            credit_account.type,
                            credit_account.pot_id,
                            new_balance,
                            cooldown_until=cooldown_until,
                            cooldown_start_balance=credit_account.cooldown_start_balance,
                            pending_drop=credit_account.pending_drop
                        )
                        credit_account.prev_balance = current_cc
                        log.info(f"Deposited override amount {diff}, cooldown remains active until {cooldown_until}.")
                    else:
                        log.info(f"No new spending detected for {credit_account.type} during active cooldown; skipping deposit override.")
                else:
                    log.info(f"Cooldown active for {credit_account.type} (cooldown_until={cooldown_until}, cooldown_start_balance={credit_account.cooldown_start_balance}); skipping final drop deposit.")
                continue

            # Handle any pending drops or final deposit if needed when no cooldown is active
            # Added extra handling to verify no cooldown is active before depositing final drop.
            if credit_account.cooldown_until is not None:
                log.info(f"Cooldown is active for {credit_account.type} (cooldown_until={credit_account.cooldown_until}, "
                         f"cooldown_start_balance={credit_account.cooldown_start_balance}); skipping final deposit.")
            else:
                drop = pending_base - current_pot
                if drop > 0:
                    selection = monzo_account.get_account_type(credit_account.pot_id)
                    log.info(f"Depositing final drop of {drop} into pot {credit_account.pot_id} for {credit_account.type}.")
                    monzo_account.add_to_pot(credit_account.pot_id, drop, account_selection=selection)
                    new_balance = monzo_account.get_pot_balance(credit_account.pot_id)
                    account_repository.update_credit_account_fields(
                        credit_account.type,
                        credit_account.pot_id,
                        new_balance,
                        cooldown_until=None,
                        cooldown_start_balance=None,
                        pending_drop=credit_account.pending_drop
                    )
                    credit_account.prev_balance = new_balance
                    credit_account.cooldown_start_balance = None
                    log.info(f"Final deposit completed, new pot balance={new_balance}")
                else:
                    log.info(f"No pending drop for {credit_account.type}.")

            # Optionally clear or update baseline if the card balance changed,
            # but only if no cooldown is active.
            if current_cc != prev_cc:
                if credit_account.cooldown_until is None:
                    log.info(f"Baseline changed from {prev_cc} to {current_cc} for {credit_account.type}.")
                    account_repository.update_credit_account_fields(
                        credit_account.type,
                        credit_account.pot_id,
                        current_pot,
                        cooldown_until=None,
                        cooldown_start_balance=None,
                        pending_drop=credit_account.pending_drop
                    )
                    credit_account.prev_balance = current_cc
                    credit_account.cooldown_start_balance = None
                else:
                    log.info(f"Cooldown active for {credit_account.type}; skipping baseline update.")
            else:
                log.info(f"No baseline update needed for {credit_account.type}.")

        log.info("Final re‑check loop complete.")
