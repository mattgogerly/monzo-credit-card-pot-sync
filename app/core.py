import logging

from sqlalchemy.exc import NoResultFound

from app.domain.accounts import MonzoAccount, TrueLayerAccount
from app.errors import AuthException
from app.extensions import db, scheduler
from app.models.account_repository import SqlAlchemyAccountRepository
from app.models.setting_repository import SqlAlchemySettingRepository

log = logging.getLogger("core")

account_repository = SqlAlchemyAccountRepository(db)
settings_repository = SqlAlchemySettingRepository(db)


# This is the core logic for the application. It's called by the scheduler on an interval.
# 1. Fetch all accounts from the database
# 2. Determine the designated pot owned by the Monzo account
# 3. Calculate the total balance of the credit accounts
# 4. Move the difference from the Monzo account to the pot
def sync_balance():
    with scheduler.app.app_context():
        # 1
        try:
            log.info("Retrieving Monzo connection")
            monzo_account: MonzoAccount = account_repository.get_monzo_account()

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
                log.info(f"Checking health of {credit_account.type} connection")
                credit_account.ping()
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

        # 2
        try:
            log.info("Retrieving ID of designated credit card pot")
            pot_id = settings_repository.get("credit_card_pot_id")
            if not pot_id:
                raise NoResultFound()

            log.info("Retrieving balance of credit card pot")
            pot_balance = monzo_account.get_pot_balance(pot_id)
            log.info(f"Credit card pot balance is £{pot_balance / 100}")
        except NoResultFound:
            log.error("No designated credit card pot configured; exiting sync loop")
            return

        # 3
        credit_balance = 0
        for credit_account in credit_accounts:
            balance = credit_account.get_total_balance()
            log.info(f"Total {credit_account.type} card balance: £{balance / 100}")
            credit_balance += balance

        log.info(f"Total credit card balance is £{balance / 100}")

        # 4
        if credit_balance == pot_balance:
            log.info("Credit card & pot balances are equal, nothing to sync")
        elif credit_balance > pot_balance:
            difference = credit_balance - pot_balance
            log.info(f"Adding £{difference / 100} to pot to sync balance")
            monzo_account.add_to_pot(pot_id, difference)
        else:
            difference = pot_balance - credit_balance
            log.info(f"Withdrawing £{difference / 100} from pot to sync balance")
            monzo_account.withdraw_from_pot(pot_id, difference)
