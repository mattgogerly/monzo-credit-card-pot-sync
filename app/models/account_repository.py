from sqlalchemy import not_
from sqlalchemy.exc import NoResultFound

from app.domain.accounts import MonzoAccount
from app.models.account import AccountModel


class SqlAlchemyAccountRepository:
    def __init__(self, db):
        self._session = db.session

    def get_all_monzo_accounts(self):
        return self._session.query(AccountModel).filter_by(type='Monzo').all()

    def get_monzo_account(self, account_type="uk_retail") -> MonzoAccount:
        result: AccountModel = (
            self._session.query(AccountModel)
            .filter_by(type="Monzo", account_type=account_type)
            .one()
        )
        return self._to_domain(result)

    def save(self, account: MonzoAccount) -> None:
        model = self._to_model(account)
        self._session.add(model)
        self._session.commit()

    def delete(self, account_type: str) -> None:
        self._session.query(AccountModel).filter_by(type=account_type).delete()
        self._session.commit()

    def _to_domain(self, model: AccountModel) -> MonzoAccount:
        return MonzoAccount(
            model.access_token,
            model.refresh_token,
            model.token_expiry,
            model.pot_id,
        )

    def _to_model(self, account: MonzoAccount) -> AccountModel:
        return AccountModel(
            type=account.type,
            access_token=account.access_token,
            refresh_token=account.refresh_token,
            token_expiry=account.token_expiry,
            pot_id=account.pot_id,
        )
