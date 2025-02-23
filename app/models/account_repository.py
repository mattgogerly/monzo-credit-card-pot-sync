from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import not_
from sqlalchemy.exc import NoResultFound

from app.domain.accounts import Account, MonzoAccount, TrueLayerAccount
from app.models.account import AccountModel


class SqlAlchemyAccountRepository:
    def __init__(self, db: SQLAlchemy) -> None:
        self._session = db.session

    def _to_model(self, account: Account) -> AccountModel:
        return AccountModel(
            type=account.type,
            access_token=account.access_token,
            refresh_token=account.refresh_token,
            token_expiry=account.token_expiry,
            pot_id=account.pot_id,
            account_id=account.account_id,
            cooldown_until=account.cooldown_until,
            prev_balance=account.prev_balance if isinstance(account.prev_balance, int) else 0,
            cooldown_ref_card_balance=account.cooldown_ref_card_balance,
            cooldown_ref_pot_balance=account.cooldown_ref_pot_balance,
            stable_pot_balance=account.stable_pot_balance
        )

    def _to_domain(self, model: AccountModel) -> Account:
        return Account(
            type=model.type,
            access_token=model.access_token,
            refresh_token=model.refresh_token,
            token_expiry=model.token_expiry,
            pot_id=model.pot_id,
            account_id=model.account_id,
            cooldown_until=(int(model.cooldown_until) if model.cooldown_until is not None else None),
            prev_balance=model.prev_balance,
            cooldown_ref_card_balance=model.cooldown_ref_card_balance,
            cooldown_ref_pot_balance=model.cooldown_ref_pot_balance,
            stable_pot_balance=model.stable_pot_balance
        )

    def get_all(self) -> list[Account]:
        results: list[AccountModel] = self._session.query(AccountModel).all()
        return list(map(self._to_domain, results))

    def get_monzo_account(self) -> MonzoAccount:
        result: AccountModel = (
            self._session.query(AccountModel).filter_by(type="Monzo").one()
        )
        account = self._to_domain(result)
        return MonzoAccount(
            account.access_token,
            account.refresh_token,
            account.token_expiry,
            account.pot_id,
            account_id=account.account_id,
            prev_balance=account.prev_balance
        )

    def get_credit_accounts(self) -> list[TrueLayerAccount]:
        results: list[AccountModel] = (
            self._session.query(AccountModel)
            .filter(not_(AccountModel.type.contains("Monzo")))
            .all()
        )
        accounts = list(map(self._to_domain, results))
        return [
            TrueLayerAccount(
                a.type,
                a.access_token,
                a.refresh_token,
                a.token_expiry,
                a.pot_id,
                prev_balance=a.prev_balance,
                stable_pot_balance=a.stable_pot_balance
            )
            for a in accounts
        ]

    def get(self, type: str) -> Account:
        result: AccountModel = (
            self._session.query(AccountModel).filter_by(type=type).one_or_none()
        )
        if result is None:
            # Log the issue and handle gracefully
            raise NoResultFound(f"Account with type '{type}' not found.")
        return self._to_domain(result)

    def save(self, account: Account) -> None:
        # Check if an account with the same type exists
        existing = self._session.query(AccountModel).filter_by(type=account.type).one_or_none()
        if existing:
            # Update existing record
            existing.access_token = account.access_token
            existing.refresh_token = account.refresh_token
            existing.token_expiry = account.token_expiry
            existing.pot_id = account.pot_id
            existing.account_id = account.account_id
            existing.prev_balance = account.prev_balance
            # Only overwrite the cooldown fields if the domain object is explicitly setting them
            if account.cooldown_until is not None:
                existing.cooldown_until = account.cooldown_until
            # If needed, do the same for cooldown_ref_card_balance or others:
            # if account.cooldown_ref_card_balance is not None:
            #     existing.cooldown_ref_card_balance = account.cooldown_ref_card_balance
            existing.cooldown_ref_pot_balance = account.cooldown_ref_pot_balance
            existing.stable_pot_balance = account.stable_pot_balance
        else:
            # No record exists, add new.
            model = self._to_model(account)
            self._session.merge(model)
        self._session.commit()

    def delete(self, type: str) -> None:
        self._session.query(AccountModel).filter_by(type=type).delete()
        self._session.commit()

    def update_credit_account_fields(self, account_type: str, pot_id: str, 
                                     new_balance: int, cooldown_until: int = None) -> Account:
        record: AccountModel = self._session.query(AccountModel).filter_by(type=account_type).one()
        record.prev_balance = new_balance
        # Only update the cooldown value if explicitly provided.
        if cooldown_until is not None:
            record.cooldown_until = cooldown_until
        else:
            # Retain existing cooldown if new value is not provided.
            record.cooldown_until = record.cooldown_until
        self._session.commit()
        return self._to_domain(record)