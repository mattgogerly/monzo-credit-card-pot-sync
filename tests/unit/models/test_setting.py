from app.models.setting import SettingModel

def test_setting_model_creation():
    setting = SettingModel(key="key", value="value")
    assert setting.key == "key"
    assert setting.value == "value"