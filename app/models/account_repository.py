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
            prev_balance=account.prev_balance if isinstance(account.prev_balance, int) else 0
        )

    def _to_domain(self, model: AccountModel) -> Account:
        return Account(
            type=model.type,
            access_token=model.access_token,
            refresh_token=model.refresh_token,
            token_expiry=model.token_expiry,
            pot_id=model.pot_id,
            account_id=model.account_id,
            cooldown_until=model.cooldown_until,
            prev_balance=model.prev_balance
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
                a.type, a.access_token, a.refresh_token, a.token_expiry, a.pot_id, prev_balance=a.prev_balance
            )
            for a in accounts
        ]

    def get(self, type: str) -> Account:
        try:
            result: AccountModel = (
                self._session.query(AccountModel).filter_by(type=type).one()
            )
        except NoResultFound:
            raise NoResultFound(type)
        return self._to_domain(result)

    def save(self, account: Account) -> None:
        model = self._to_model(account)
        self._session.merge(model)
        self._session.commit()

    def delete(self, type: str) -> None:
        self._session.query(AccountModel).filter_by(type=type).delete()
        self._session.commit()

    def update_credit_account_fields(self, account_type: str, pot_id: str, new_balance: int, cooldown_until: int = None) -> None:
        record: AccountModel = self._session.query(AccountModel).filter_by(type=account_type).one()
        record.prev_balance = new_balance
        if cooldown_until is not None:
            record.cooldown_until = cooldown_until
        self._session.commit()