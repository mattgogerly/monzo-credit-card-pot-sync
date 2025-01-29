import logging

from sqlalchemy.exc import NoResultFound

from app.domain.accounts import MonzoAccount, TrueLayerAccount
from app.domain.settings import Setting
from app.errors import AuthException
from app.extensions import db, scheduler
from app.models.account_repository import SqlAlchemyAccountRepository
from app.models.setting_repository import SqlAlchemySettingRepository

log = logging.getLogger("core")

account_repository = SqlAlchemyAccountRepository(db)
settings_repository = SqlAlchemySettingRepository(db)


# This is the core logic for the application. It's called by the scheduler on an interval.
# 1. Fetch all accounts from the database and validate health of the connections
# 2. For each account:
#  a. Determine the designated pot for the account, and get the balance if not already retrieved
#  b. Get the balance of the credit account
#  c. Update the difference between the pot balance and this credit account balance
# 3. For each pot:
#  a. Get the balance of the Monzo account, so we can check if there's enough money to move
#  b. Move the difference from the Monzo account to or from the pot
def sync_balance():
    with scheduler.app.app_context():
        # 1
        try:
            log.info("Retrieving Monzo connection")
            monzo_account: MonzoAccount = account_repository.get_monzo_account()

            log.info("Checking if Monzo access token needs refreshing")
            if monzo_account.is_token_within_expiry_window():
                monzo_account.refresh_access_token()
                account_repository.save(monzo_account)

            log.info("Checking health of Monzo connection")
            monzo_account.ping()
            log.info("Monzo connection is healthy")
        except NoResultFound:
            log.error("No Monzo connection configured; sync will not run")
            monzo_account = None
        except AuthException:
            log.error(
                "Failed to check health of Monzo connection; connection will be removed & sync will not run"
            )
            account_repository.delete(monzo_account.type)
            monzo_account = None

        log.info("Retrieving credit card connections")
        credit_accounts: list[TrueLayerAccount] = (
            account_repository.get_credit_accounts()
        )
        log.info(f"Retrieved {len(credit_accounts)} credit card connections")
        for credit_account in credit_accounts:
            try:
                log.info(
                    f"Checking if {credit_account.type} access token needs refreshing"
                )
                if credit_account.is_token_within_expiry_window():
                    credit_account.refresh_access_token()
                    account_repository.save(credit_account)

                log.info(f"Checking health of {credit_account.type} connection")
                credit_account.ping()
                log.info(f"{credit_account.type} connection is healthy")
            except AuthException:
                log.error(
                    f"Failed to check health of {credit_account.type} connection; connection will be removed"
                )

                if monzo_account is not None:
                    monzo_account.send_notification(
                        f"{credit_account.type} Pot Sync Access Expired",
                        "Reconnect the account(s) on your Monzo Credit Card Pot Sync portal to resume sync",
                    )

                account_repository.delete(credit_account)

        # nothing to sync, so exit now
        if monzo_account is None or len(credit_accounts) == 0:
            log.info(
                "Either Monzo connection is invalid, or there are no valid credit card connections; exiting sync loop"
            )
            return

        if not settings_repository.get("enable_sync"):
            log.info("Balance sync is disabled; exiting sync loop")
            return

        # Map to store pot balance differentials
        pot_balance_map = {}

        # 2
        for credit_account in credit_accounts:
            # 2a
            try:
                pot_id = credit_account.pot_id
                if not pot_id:
                    raise NoResultFound()

                if pot_id not in pot_balance_map:
                    log.info(f"Retrieving balance of credit card pot {pot_id}")
                    pot_balance = monzo_account.get_pot_balance(pot_id)
                    pot_balance_map[pot_id] = pot_balance
                    log.info(
                        f"Credit card pot {pot_id} balance is £{pot_balance / 100}"
                    )
            except NoResultFound:
                log.error(
                    f"No designated credit card pot configured for {credit_account.type}; exiting sync loop"
                )
                return

            # 2b
            log.info(f"Retrieving balance of {credit_account.type} card")
            credit_balance = credit_account.get_total_balance()
            log.info(f"{credit_account.type} card balance is £{credit_balance / 100}")

            # 2c subtract balance of this card from designated pot balance
            pot_balance_map[pot_id] -= credit_balance

        # 3
        for pot_id, pot_balance in pot_balance_map.items():
            # 3a
            try:
                log.info("Retrieving balance of Monzo account")
                account_balance = monzo_account.get_balance()
                log.info(f"Monzo account balance is £{account_balance / 100}")
            except AuthException:
                log.error("Failed to retrieve Monzo account balance; exiting sync loop")
                return

            log.info(f"Pot {pot_id} balance difference is £{pot_balance / 100}")

            # 3b
            if pot_balance == 0:
                log.info("Credit card & pot balances are equal, nothing to sync")
            elif pot_balance < 0:
                difference = abs(pot_balance)
                if account_balance < difference:
                    log.error(
                        "Monzo account balance is insufficient to sync pot; exiting sync loop"
                    )
                    settings_repository.save(Setting("enable_sync", "False"))
                    monzo_account.send_notification(
                        "Balance Insufficient To Sync Credit Card Pot",
                        "Sync has been disabled. Top up your Monzo account and re-enable to resume syncing with your credit card pot(s)",
                    )
                    return

                log.info(
                    f"Adding £{difference / 100} to credit card pot {pot_id} to sync balance"
                )
                monzo_account.add_to_pot(pot_id, difference)
            else:
                difference = abs(pot_balance)
                log.info(
                    f"Withdrawing £{difference / 100} from credit card pot {pot_id} to sync balance"
                )
                monzo_account.withdraw_from_pot(pot_id, difference)
