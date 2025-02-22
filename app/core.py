"""
Core Sync Process Overview:

SECTION 1: INITIALIZATION AND CONNECTION VALIDATION
    - Retrieve and validate the Monzo account.
    - Refresh token if necessary and ping the connection.

SECTION 2: RETRIEVE AND VALIDATE CREDIT ACCOUNTS
    - Retrieve credit card connections.
    - Refresh tokens and validate health.
    - Remove accounts with auth issues.

SECTION 3: CALCULATE BALANCE DIFFERENTIALS PER POT
    - Build a mapping of pots with their live balance minus credit card balances.

SECTION 4: REFRESH PERSISTED ACCOUNT DATA
    - Reload each credit account's persisted fields (cooldown, prev_balance).

SECTION 5: EXPIRED COOLDOWN CHECK
    - For accounts with an expired cooldown, compute the shortfall.
      Branch: If shortfall exists, deposit it and clear cooldown; otherwise, simply clear cooldown.

SECTION 6: PER-ACCOUNT BALANCE ADJUSTMENT PROCESSING (DEPOSIT / WITHDRAWAL)
    - Process each credit account sequentially:
         (a) OVERRIDE BRANCH: If override flag is enabled and cooldown is active,
             deposit the difference immediately if card balance > previous balance.
         (b) STANDARD ADJUSTMENT: Compare live card vs. pot balance.
             – Deposit if card > pot.
             – Withdraw if card < pot.
             – Do nothing if equal.

SECTION 7: FINAL DEPOSIT RE-CHECK (AFTER COOLDOWN)
    - After an extra delay post-cooldown expiration, check for any residual shortfall (drop)
      and deposit it if needed.

SECTION 8: UPDATE BASELINE PERSISTENCE
    - For each account, if a confirmed change is detected (card balance ≠ previous balance) and not in cooldown,
      update the persisted baseline with the current card balance.
"""

import logging
from sqlalchemy.exc import NoResultFound
from time import time
import datetime  # Needed for human-readable time conversions

from app.domain.accounts import MonzoAccount, TrueLayerAccount
from app.errors import AuthException
from app.extensions import db, scheduler
from app.models.account_repository import SqlAlchemyAccountRepository
from app.models.setting_repository import SqlAlchemySettingRepository
from app.domain.settings import Setting

log = logging.getLogger("core")
account_repository = SqlAlchemyAccountRepository(db)
settings_repository = SqlAlchemySettingRepository(db)

# Add helper function for converting settings to a boolean
def bool_from_setting(value) -> bool:
    return str(value).strip().lower() in ("true", "1", "yes")

def sync_balance():
    with scheduler.app.app_context():
        # --------------------------------------------------------------------
        # SECTION 1: INITIALIZATION AND CONNECTION VALIDATION
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
                # Suppose the exception carries a details attribute
                details = getattr(e, 'details', {})
                description = details.get('error_description', '')
                if "currently unavailable" in description or details.get('error') == 'provider_error':
                    log.info(f"Service provider for {credit_account.type} is currently unavailable, will retry later.")
                else:
                    if monzo_account is not None:
                        monzo_account.send_notification(
                            f"{credit_account.type} Pot Sync Access Expired",
                            "Reconnect the account(s) on your Monzo Credit Card Pot Sync portal to resume sync",
                        )
                    account_repository.delete(credit_account.type)
       
        if (monzo_account is None or len(credit_accounts) == 0):
            log.info("Either Monzo connection is invalid, or there are no valid credit card connections; exiting sync loop")
            return

        # --------------------------------------------------------------------
        # SECTION 3: CALCULATE BALANCE DIFFERENTIALS PER POT
        # --------------------------------------------------------------------
        pot_balance_map = {}
        for credit_account in credit_accounts:
            try:
                pot_id = credit_account.pot_id
                if (not pot_id):
                    raise NoResultFound(f"No designated credit card pot set for {credit_account.type}")
                account_selection = monzo_account.get_account_type(pot_id)
                if (pot_id not in pot_balance_map):
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

        if (not settings_repository.get("enable_sync")):
            log.info("Balance sync is disabled; exiting sync loop")
            return

        # --------------------------------------------------------------------
        # SECTION 4: REFRESH PERSISTED ACCOUNT DATA
        # --------------------------------------------------------------------
        for i, credit_account in enumerate(credit_accounts):
            refreshed = account_repository.get(credit_account.type)
            credit_accounts[i].cooldown_until = refreshed.cooldown_until
            credit_accounts[i].prev_balance = refreshed.prev_balance
        log.info("Refreshed credit account data including cooldown values.")

        # --------------------------------------------------------------------
        # SECTION 5: EXPIRED COOLDOWN CHECK
        # --------------------------------------------------------------------
        now = int(time())
        for credit_account in credit_accounts:
            if (credit_account.pot_id and credit_account.cooldown_until and now >= credit_account.cooldown_until):
                log.info(f"[Cooldown Expiration] {credit_account.type}: Expired cooldown detected.")
                pre_deposit = credit_account.get_prev_balance(credit_account.pot_id)
                current_pot = monzo_account.get_pot_balance(credit_account.pot_id)
                baseline = (
                    credit_account.cooldown_ref_card_balance
                    if credit_account.cooldown_ref_card_balance is not None
                    else pre_deposit
                )
                drop = baseline - current_pot
                if (drop > 0):
                    log.info(f"[Cooldown Expiration] {credit_account.type}: Depositing shortfall of £{drop / 100:.2f} for pot {credit_account.pot_id}.")
                    selection = monzo_account.get_account_type(credit_account.pot_id)
                    # NEW: Check if enough funds in Monzo account before deposit
                    available_funds = monzo_account.get_balance(selection)
                    if available_funds < drop:
                        insufficent_diff = drop - available_funds
                        log.error(f"Insufficient funds in Monzo account to sync pot; required: £{drop/100:.2f}, available: £{available_funds/100:.2f}; diff required £{insufficent_diff/100:.2f}; disabling sync")
                        settings_repository.save(Setting("enable_sync", "False"))
                        monzo_account.send_notification(
                            f"Lacking £{insufficent_diff/100:.2f} - Insufficient Funds, Sync Disabled",
                            f"Sync disabled due to insufficient funds. Required deposit: £{drop/100:.2f}, available: £{available_funds/100:.2f}. Please top up at least £{insufficent_diff/100:.2f} and re-enable sync.",
                            account_selection=selection
                        )
                        continue
                    monzo_account.add_to_pot(credit_account.pot_id, drop, account_selection=selection)
                    new_balance = monzo_account.get_pot_balance(credit_account.pot_id)
                    credit_account.stable_pot_balance = new_balance
                    credit_account.prev_balance = new_balance
                    credit_account.cooldown_until = None
                    credit_account.cooldown_ref_card_balance = None
                    account_repository.update_credit_account_fields(
                        credit_account.type, credit_account.pot_id, new_balance, None
                    )
                    log.info(f"[Cooldown Expiration] {credit_account.type}: Updated pot balance is £{new_balance / 100:.2f}.")
                else:
                    log.info(f"[Cooldown Expiration] {credit_account.type}: No shortfall detected; clearing cooldown.")
                    credit_account.cooldown_until = None
                    credit_account.cooldown_ref_card_balance = None
                    current_pot = monzo_account.get_pot_balance(credit_account.pot_id)
                    account_repository.update_credit_account_fields(
                        credit_account.type, credit_account.pot_id, current_pot, None
                    )

        # --------------------------------------------------------------------
        # SECTION 6: PER-ACCOUNT BALANCE ADJUSTMENT PROCESSING (DEPOSIT / WITHDRAWAL)
        # Process one account at a time with detailed logging.
        for credit_account in credit_accounts:
            log.info("-------------------------------------------------------------")
            log.info(f"Step: Start processing account '{credit_account.type}'.")
            refreshed = account_repository.get(credit_account.type)
            credit_account.cooldown_until = refreshed.cooldown_until
            credit_account.prev_balance = refreshed.prev_balance

            # Retrieve current live figures
            live_card_balance = credit_account.get_total_balance()
            current_pot = monzo_account.get_pot_balance(credit_account.pot_id)
            stable_pot = credit_account.stable_pot_balance if credit_account.stable_pot_balance is not None else 0

            # Log current account and pot status details
            log.info(
                f"Account '{credit_account.type}': Live Card Balance = £{live_card_balance / 100:.2f}; "
                f"Previous Card Baseline = £{credit_account.prev_balance / 100:.2f}."
            )
            log.info(
                f"Pot '{credit_account.pot_id}': Current Pot Balance = £{current_pot / 100:.2f}; "
                f"Stable Pot Balance = £{stable_pot / 100:.2f}."
            )
            if credit_account.cooldown_until:
                hr_cooldown = datetime.datetime.fromtimestamp(credit_account.cooldown_until).strftime("%Y-%m-%d %H:%M:%S")
                if int(time()) < credit_account.cooldown_until:
                    log.info(f"Cooldown active until {hr_cooldown} (epoch: {credit_account.cooldown_until}).")
                else:
                    log.info(f"Cooldown expired at {hr_cooldown} (epoch: {credit_account.cooldown_until}).")
            else:
                log.info("No active cooldown on this account.")

            # Log debug information before the cooldown check
            if credit_account.cooldown_until is not None:
                hr_cooldown = datetime.datetime.fromtimestamp(credit_account.cooldown_until).strftime("%Y-%m-%d %H:%M:%S")
                log.debug(
                    f"Before adjustment: credit_account.prev_balance={credit_account.prev_balance}, "
                    f"live_card_balance={live_card_balance}, current_pot={current_pot}, "
                    f"cooldown_until={hr_cooldown}"
                )
            else:
                log.debug(
                    f"Before adjustment: credit_account.prev_balance={credit_account.prev_balance}, "
                    f"live_card_balance={live_card_balance}, current_pot={current_pot}, "
                    f"cooldown_until=None"
                )

            # (a) OVERRIDE BRANCH
            if (settings_repository.get("override_cooldown_spending") == "True" and credit_account.cooldown_until and int(time()) < credit_account.cooldown_until):
                log.info("Step: OVERRIDE branch activated due to cooldown flag.")
                selection = monzo_account.get_account_type(credit_account.pot_id)
                # Calculate deposit as the additional spending since the previous baseline.
                diff = live_card_balance - credit_account.prev_balance
                if diff > 0:
                    monzo_account.add_to_pot(credit_account.pot_id, diff, account_selection=selection)
                    log.info(
                        f"[Override] {credit_account.type}: Override deposit of £{diff/100:.2f} executed "
                        f"as card increased from £{credit_account.prev_balance/100:.2f} to £{live_card_balance/100:.2f}."
                    )
                    # Update card baseline but keep the previous shortfall queued (cooldown remains active).
                    credit_account.prev_balance = live_card_balance
                    account_repository.save(credit_account)
                log.info(f"Step: Finished OVERRIDE branch for account '{credit_account.type}'.")

            # (b) STANDARD ADJUSTMENT:
            if live_card_balance > credit_account.prev_balance:
                log.info("Step: Regular spending detected (card balance increased).")
                diff = live_card_balance - current_pot
                selection = monzo_account.get_account_type(credit_account.pot_id)
                # NEW: Check if enough funds in Monzo account before depositing the difference
                available_funds = monzo_account.get_balance(selection)
                if available_funds < diff:
                    insufficent_diff = diff - available_funds
                    log.error(f"Insufficient funds in Monzo account to sync pot; required: £{diff/100:.2f}, available: £{available_funds/100:.2f}; diff required £{insufficent_diff/100:.2f}; disabling sync")
                    settings_repository.save(Setting("enable_sync", "False"))
                    monzo_account.send_notification(
                        f"Lacking £{insufficent_diff/100:.2f} - Insufficient Funds, Sync Disabled",
                        f"Sync disabled due to insufficient funds. Required deposit: £{diff/100:.2f}, available: £{available_funds/100:.2f}. Please top up at least £{insufficent_diff/100:.2f} and re-enable sync.",
                        account_selection=selection
                    )
                    continue
                monzo_account.add_to_pot(credit_account.pot_id, diff, account_selection=selection)
                new_pot = monzo_account.get_pot_balance(credit_account.pot_id)
                log.info(
                    f"[Standard] {credit_account.type}: Deposited £{diff / 100:.2f}."
                    f"Pot updated from £{current_pot / 100:.2f} to £{new_pot / 100:.2f}; card increased from £{credit_account.prev_balance / 100:.2f} to £{live_card_balance / 100:.2f}."
                )
                credit_account.prev_balance = live_card_balance
                account_repository.update_credit_account_fields(credit_account.type, credit_account.pot_id, live_card_balance, None)
            elif live_card_balance == credit_account.prev_balance:
                log.info("Step: No increase in card balance detected.")
                if current_pot < live_card_balance:
                    if not bool_from_setting(settings_repository.get("enable_sync")):
                        log.info(f"[Standard] {credit_account.type}: Sync disabled; not initiating cooldown.")
                    elif credit_account.cooldown_until is None or credit_account.cooldown_until <= int(time()):
                        log.info("Situation: Pot dropped below card balance without confirmed spending.")
                        try:
                            cooldown_hours = int(settings_repository.get("deposit_cooldown_hours"))
                        except Exception:
                            cooldown_hours = 3
                        new_cooldown = int(time()) + cooldown_hours * 3600
                        credit_account.cooldown_until = new_cooldown
                        hr_cooldown = datetime.datetime.fromtimestamp(new_cooldown).strftime("%Y-%m-%d %H:%M:%S")
                        log.info(
                            f"[Standard] {credit_account.type}: Initiating cooldown because pot (£{current_pot / 100:.2f}) is less than card (£{live_card_balance / 100:.2f} pence). "
                            f"Cooldown set until {hr_cooldown} (epoch: {new_cooldown})."
                        )
                        account_repository.save(credit_account)
                    else:
                        log.info(f"[Standard] {credit_account.type}: Card and pot balance unchanged; no action taken.")
                else:
                    log.info(f"[Standard] {credit_account.type}: Card and pot balance unchanged; no action taken.")
            elif live_card_balance < current_pot:
                log.info("Step: Withdrawal due to pot exceeding card balance.")
                diff = current_pot - live_card_balance
                selection = monzo_account.get_account_type(credit_account.pot_id)
                monzo_account.withdraw_from_pot(credit_account.pot_id, diff, account_selection=selection)
                new_pot = monzo_account.get_pot_balance(credit_account.pot_id)
                log.info(
                    f"[Standard] {credit_account.type}: Withdrew £{diff / 100:.2f} as pot exceeded card. "
                    f"Pot changed from £{current_pot / 100:.2f} to £{new_pot / 100:.2f} while card remains at £{live_card_balance / 100:.2f}."
                )
                credit_account.prev_balance = live_card_balance
                account_repository.save(credit_account)

            log.info(f"Step: Finished processing account '{credit_account.type}'.")
            log.info("-------------------------------------------------------------")

        # --------------------------------------------------------------------
        # SECTION 7: FINAL DEPOSIT RE-CHECK (AFTER COOLDOWN)
        # --------------------------------------------------------------------
        EXTRA_WAIT_SECONDS = 600  # e.g. 10 minutes delay after cooldown expiration
        for credit_account in credit_accounts:
            if (credit_account.pot_id and credit_account.cooldown_until):
                if (int(time()) < credit_account.cooldown_until + EXTRA_WAIT_SECONDS):
                    human_readable = datetime.datetime.fromtimestamp(
                        credit_account.cooldown_until + EXTRA_WAIT_SECONDS
                    ).strftime("%Y-%m-%d %H:%M:%S")
                    log.info(f"[Final Re-check] Waiting until at least {human_readable} before re‑check for {credit_account.type}.")
                    continue
                pre_deposit = credit_account.get_prev_balance(credit_account.pot_id)
                current_balance = monzo_account.get_pot_balance(credit_account.pot_id)
                baseline = (
                    credit_account.cooldown_ref_card_balance
                    if credit_account.cooldown_ref_card_balance is not None
                    else pre_deposit
                )
                drop = baseline - current_balance
                if (drop > 0):
                    log.info(f"[Final Re-check] Depositing pending drop of £{drop / 100:.2f} for {credit_account.type} into pot {credit_account.pot_id}.")
                    selection = monzo_account.get_account_type(credit_account.pot_id)
                    monzo_account.add_to_pot(credit_account.pot_id, drop, account_selection=selection)
                    new_balance = monzo_account.get_pot_balance(credit_account.pot_id)
                    credit_account.stable_pot_balance = new_balance
                    account_repository.update_credit_account_fields(credit_account.type, credit_account.pot_id, new_balance, None)
                    credit_account.prev_balance = new_balance
                else:
                    log.info(f"[Final Re-check] No residual drop for {credit_account.type} after cooldown; no deposit executed.")

        # --------------------------------------------------------------------
        # SECTION 8: UPDATE BASELINE PERSISTENCE
        # --------------------------------------------------------------------
        current_time = int(time())
        for credit_account in credit_accounts:
            if (credit_account.pot_id):
                live = credit_account.get_total_balance()
                prev = credit_account.get_prev_balance(credit_account.pot_id)
                if (credit_account.cooldown_until and current_time < credit_account.cooldown_until):
                    log.info(f"[Baseline Update] {credit_account.type}: Cooldown active; baseline not updated.")
                    continue
                if (live != prev):
                    log.info(f"[Baseline Update] {credit_account.type}: Updating baseline from £{prev / 100:.2f} to £{live / 100:.2f}.")
                    account_repository.update_credit_account_fields(credit_account.type, credit_account.pot_id, live)
                    credit_account.prev_balance = live
                else:
                    log.info(f"[Baseline Update] {credit_account.type}: Baseline remains unchanged (prev: £{prev / 100:.2f}, live: £{live / 100:.2f}).")

        # --------------------------------------------------------------------
        # END OF SYNC LOOP
        # --------------------------------------------------------------------
        log.info("All credit accounts processed.")