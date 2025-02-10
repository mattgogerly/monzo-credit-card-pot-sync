from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import NoResultFound

from app.domain.settings import Setting
from app.models.setting import SettingModel

class SqlAlchemySettingRepository:
    def __init__(self, db: SQLAlchemy) -> None:
        self._db = db

    def _to_model(self, setting: Setting) -> SettingModel:
        return SettingModel(
            key=setting.key,
            value=setting.value
        )

    def _to_domain(self, model: SettingModel) -> Setting:
        return Setting(
            key=model.key,
            value=model.value
        )

    def get(self, key: str) -> Setting:
        try:
            result: SettingModel = (
                self._db.session.query(SettingModel).filter_by(key=key).one()
            )
        except NoResultFound:
            raise NoResultFound(f"No setting found for key: {key}")
        return self._to_domain(result)

    def save(self, setting: Setting) -> None:
        model = self._to_model(setting)
        existing_setting = self._db.session.query(SettingModel).filter_by(key=setting.key).first()
        if existing_setting:
            self._db.session.delete(existing_setting)
        self._db.session.add(model)
        self._db.session.commit()