from flask_sqlalchemy import SQLAlchemy
from app.domain.settings import Setting
from app.models.setting import SettingModel

class SqlAlchemySettingRepository:
    def __init__(self, db: SQLAlchemy) -> None:
        self._session = db.session

    def _to_model(self, setting: Setting) -> SettingModel:
        return SettingModel(key=setting.key, value=setting.value)

    def _to_domain(self, model: SettingModel) -> Setting:
        # Convert the string 'True' or 'False' to a boolean
        if model.value in ["True", "False"]:
            return Setting(key=model.key, value=model.value == "True")
        return Setting(key=model.key, value=model.value)

    def get_all(self) -> list[Setting]:
        results: list[SettingModel] = self._session.query(SettingModel).all()
        return list(map(self._to_domain, results))

    def get(self, key: str) -> Setting:
        result: SettingModel = (
            self._session.query(SettingModel).filter_by(key=key).one()
        )
        return self._to_domain(result).value

    def save(self, setting: Setting) -> None:
        model = self._to_model(setting)
        self._session.merge(model)
        self._session.commit()
