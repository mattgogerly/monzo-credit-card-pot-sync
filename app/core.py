import logging
import ast
from sqlalchemy.exc import NoResultFound
from time import time
import datetime  # Needed for human-readable time conversions

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
        # Section 1–2: Connect to Monzo and validate credit accounts.
        # Section 3: Calculate differential balance for each pot.
        # Section 4: Refresh persisted fields.
        # Section 5: Immediately process expired cooldowns (deposit shortfall and clear cooldown) so that subsequent logic works on updated baselines.
        # Section 6: Standard adjustment processing (handling deposit if spending, withdrawal if payment, or nothing if balanced).
        # Section 7: Final re‑check after an extra delay on pending drop deposit (if any).
        # Section 8: Update persisted baseline so that future runs compare correctly.

        # --------------------------------------------------------------------
        # SECTION 1: INITIALIZATION AND CONNECTION VALIDATION
        # - Retrieve and validate Monzo connection.
        # - Refresh token if needed and ping the connection.
        # --------------------------------------------------------------------
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

        # --------------------------------------------------------------------
        # SECTION 2: RETRIEVE AND VALIDATE CREDIT ACCOUNTS
        # - Retrieve credit card connections.
        # - Refresh tokens and validate each connection.
        # - Remove accounts with authentication issues.
        # --------------------------------------------------------------------
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
                # If the error indicates provider unavailability, skip; otherwise, remove the account.
                if "currently unavailable" not in error_message:
                    if monzo_account is not None:
                        monzo_account.send_notification(
                            f"{credit_account.type} Pot Sync Access Expired",
                            "Reconnect the account(s) on your Monzo Credit Card Pot Sync portal to resume sync",
                        )
                    account_repository.delete(credit_account.type)
                else:
                    log.info(f"Service provider for {credit_account.type} is currently unavailable, will retry later.")

        if monzo_account is None or len(credit_accounts) == 0:
            log.info("Either Monzo connection is invalid, or there are no valid credit card connections; exiting sync loop")
            return

        # --------------------------------------------------------------------
        # SECTION 3: CALCULATE BALANCE DIFFERENTIALS PER POT
        # - Build a mapping for each pot showing its live balance differential
        #   by subtracting the aggregated credit card balances.
        # --------------------------------------------------------------------
        pot_balance_map = {}
        for credit_account in credit_accounts:
            try:
                pot_id = credit_account.pot_id
                if not pot_id:
                    raise NoResultFound(f"No designated credit card pot set for {credit_account.type}")
                account_selection = monzo_account.get_account_type(pot_id)
                if pot_id not in pot_balance_map:
                    log.info(f"Retrieving balance for credit card pot {pot_id}")
                    pot_balance = monzo_account.get_pot_balance(pot_id)
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
            pot_balance_map[credit_account.pot_id]['balance'] -= credit_balance

        if not settings_repository.get("enable_sync"):
            log.info("Balance sync is disabled; exiting sync loop")
            return

        # Build mapping for quick look-up later.
        pot_to_credit_account = {f"{ac.pot_id}_{ac.type}": ac for ac in credit_accounts if ac.pot_id}

        # --------------------------------------------------------------------
        # SECTION 4: REFRESH PERSISTED ACCOUNT DATA
        # - Refresh each credit account’s persisted values (cooldown, prev_balance).
        # --------------------------------------------------------------------
        for i, credit_account in enumerate(credit_accounts):
            refreshed = account_repository.get(credit_account.type)
            credit_accounts[i].cooldown_until = refreshed.cooldown_until
            credit_accounts[i].prev_balance = refreshed.prev_balance
        log.info("Refreshed credit account data including cooldown values.")

        # --------------------------------------------------------------------
        # SECTION 5: EXPIRED COOLDOWN CHECK (PROCESS BEFORE FURTHER ADJUSTMENTS)
        # - For any account with cooldown that has expired, immediately:
        #   #  a) Calculate shortfall.
        #   #  b) Deposit the shortfall.
        #   #  c) Update stable baseline and clear cooldown fields.
        # --------------------------------------------------------------------
        now = int(time())
        for credit_account in credit_accounts:
            if credit_account.pot_id and credit_account.cooldown_until and now >= credit_account.cooldown_until:
                log.info(f"[Cooldown Expiration] {credit_account.type}: Expired cooldown detected.")
                pre_deposit = credit_account.get_prev_balance(credit_account.pot_id)
                current_pot = monzo_account.get_pot_balance(credit_account.pot_id)
                baseline = credit_account.cooldown_start_balance if credit_account.cooldown_start_balance is not None else pre_deposit
                drop = baseline - current_pot
                if drop > 0:
                    log.info(f"[Cooldown Expiration] {credit_account.type}: Depositing shortfall of {drop} pence for pot {credit_account.pot_id}.")
                    selection = monzo_account.get_account_type(credit_account.pot_id)
                    monzo_account.add_to_pot(credit_account.pot_id, drop, account_selection=selection)
                    new_balance = monzo_account.get_pot_balance(credit_account.pot_id)
                    # Reset baseline to new balance and clear cooldown.
                    credit_account.stable_pot_balance = new_balance
                    credit_account.prev_balance = new_balance
                    credit_account.cooldown_until = None
                    credit_account.cooldown_start_balance = None
                    account_repository.update_credit_account_fields(
                        credit_account.type, credit_account.pot_id, new_balance, None, None, None
                    )
                    log.info(f"[Cooldown Expiration] {credit_account.type}: Updated pot balance is {new_balance}.")
                else:
                    log.info(f"[Cooldown Expiration] {credit_account.type}: No shortfall detected; clearing cooldown.")
                    credit_account.cooldown_until = None
                    credit_account.cooldown_start_balance = None
                    current_pot = monzo_account.get_pot_balance(credit_account.pot_id)
                    account_repository.update_credit_account_fields(
                        credit_account.type, credit_account.pot_id, current_pot, None, None, None
                    )

        # --------------------------------------------------------------------
        # SECTION 6: PER-ACCOUNT BALANCE ADJUSTMENT PROCESSING (DEPOSIT / WITHDRAWAL)
        # - Process each credit account sequentially.
        # - For each account:
        #    a) Refresh persisted account values.
        #    b) Retrieve live card balance and pot balance.
        #    c) If the override flag is enabled and a cooldown is active, then if the card balance 
        #       exceeds the previous balance, deposit the difference immediately (override branch).
        #    d) Otherwise, if card > pot then deposit the difference.
        #    e) If card < pot, withdraw the difference.
        #    f) If equal, do nothing.
        # --------------------------------------------------------------------
        for credit_account in credit_accounts:
            log.info(f"--- Processing account: {credit_account.type} ---")
            # Refresh persisted fields for this account.
            refreshed = account_repository.get(credit_account.type)
            credit_account.cooldown_until = refreshed.cooldown_until
            credit_account.prev_balance = refreshed.prev_balance

            # Retrieve live balances.
            live_card_balance = credit_account.get_total_balance()
            current_pot = monzo_account.get_pot_balance(credit_account.pot_id)

            # ------------------------
            # (a) OVERRIDE BRANCH:
            # If override is enabled and a cooldown is active, then
            # deposit the difference even before cooldown expires.
            # ------------------------
            if settings_repository.get("override_cooldown_spending") == "True" and credit_account.cooldown_until:
                if live_card_balance > credit_account.prev_balance:
                    diff = live_card_balance - credit_account.prev_balance
                    selection = monzo_account.get_account_type(credit_account.pot_id)
                    monzo_account.add_to_pot(credit_account.pot_id, diff, account_selection=selection)
                    log.info(f"[Override] {credit_account.type}: Override deposit of {diff} pence executed.")
                    credit_account.prev_balance = live_card_balance
                    account_repository.save(credit_account)
                    # Continue to next account; skip standard branch.
                    log.info(f"--- Finished processing account: {credit_account.type} (override applied) ---")
                    continue

            # ------------------------
            # (b) STANDARD ADJUSTMENT:
            # Check live card vs pot:
            # - If card balance exceeds pot, deposit the difference.
            # - If card balance is lower than pot, withdraw the difference.
            # ------------------------
            if live_card_balance > current_pot:
                diff = live_card_balance - current_pot
                selection = monzo_account.get_account_type(credit_account.pot_id)
                monzo_account.add_to_pot(credit_account.pot_id, diff, account_selection=selection)
                log.info(f"[Standard] {credit_account.type}: Deposited {diff} pence into pot {credit_account.pot_id}.")
                credit_account.prev_balance = live_card_balance
                account_repository.save(credit_account)
            elif live_card_balance < current_pot:
                diff = current_pot - live_card_balance
                selection = monzo_account.get_account_type(credit_account.pot_id)
                monzo_account.withdraw_from_pot(credit_account.pot_id, diff, account_selection=selection)
                log.info(f"[Standard] {credit_account.type}: Withdrew {diff} pence from pot {credit_account.pot_id}.")
                credit_account.prev_balance = live_card_balance
                account_repository.save(credit_account)
            else:
                log.info(f"[Standard] {credit_account.type}: Card and pot balance equal; no deposit or withdrawal performed.")

            log.info(f"--- Finished processing account: {credit_account.type} ---")

        # --------------------------------------------------------------------
        # SECTION 7: FINAL DEPOSIT RE-CHECK (AFTER COOLDOWN)
        # - After a delay following cooldown expiration, check for any residual pending drop.
        # - Deposit any pending shortfall and update baseline.
        # --------------------------------------------------------------------
        EXTRA_WAIT_SECONDS = 600  # e.g. 10 minutes delay after cooldown expiration
        for credit_account in credit_accounts:
            if credit_account.pot_id and credit_account.cooldown_until:
                if int(time()) < credit_account.cooldown_until + EXTRA_WAIT_SECONDS:
                    human_readable = datetime.datetime.fromtimestamp(credit_account.cooldown_until + EXTRA_WAIT_SECONDS).strftime("%Y-%m-%d %H:%M:%S")
                    log.info(f"[Final Re-check] Waiting until at least {human_readable} before re‑check for {credit_account.type}.")
                    continue
                pre_deposit = credit_account.get_prev_balance(credit_account.pot_id)
                current_balance = monzo_account.get_pot_balance(credit_account.pot_id)
                baseline = credit_account.cooldown_start_balance if credit_account.cooldown_start_balance is not None else pre_deposit
                drop = baseline - current_balance
                if drop > 0:
                    log.info(f"[Final Re-check] Depositing pending drop of {drop} for {credit_account.type} into pot {credit_account.pot_id}.")
                    selection = monzo_account.get_account_type(credit_account.pot_id)
                    monzo_account.add_to_pot(credit_account.pot_id, drop, account_selection=selection)
                    new_balance = monzo_account.get_pot_balance(credit_account.pot_id)
                    credit_account.stable_pot_balance = new_balance  # Reset baseline
                    account_repository.update_credit_account_fields(credit_account.type, credit_account.pot_id, new_balance, None, None, None)
                    credit_account.prev_balance = new_balance
                else:
                    log.info(f"[Final Re-check] No residual drop for {credit_account.type} after cooldown; no deposit executed.")

        # --------------------------------------------------------------------
        # SECTION 8: UPDATE BASELINE PERSISTENCE
        # - For accounts where there is a confirmed change (spending or payment),
        #   update persisted baseline (prev_balance) so that subsequent runs use the new value.
        # --------------------------------------------------------------------
        current_time = int(time())
        for credit_account in credit_accounts:
            if credit_account.pot_id:
                live = credit_account.get_total_balance()
                prev = credit_account.get_prev_balance(credit_account.pot_id)
                if credit_account.cooldown_until and current_time < credit_account.cooldown_until:
                    log.info(f"[Baseline Update] {credit_account.type}: Cooldown active; baseline not updated.")
                    continue
                if live != prev:
                    log.info(f"[Baseline Update] {credit_account.type}: Updating baseline from {prev} to {live}.")
                    account_repository.update_credit_account_fields(credit_account.type, credit_account.pot_id, live)
                    credit_account.prev_balance = live
                else:
                    log.info(f"[Baseline Update] {credit_account.type}: Baseline remains unchanged (prev: {prev}, live: {live}).")

        # --------------------------------------------------------------------
        # END OF SYNC LOOP – ALL ACCOUNTS PROCESSED
        # --------------------------------------------------------------------
        log.info("All credit accounts processed.")
