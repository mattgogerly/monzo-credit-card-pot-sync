from app.domain.settings import Setting


def test_new_setting():
    setting = Setting("key", "value")
    assert setting.key == "key"
    assert setting.value == "value"


def test_setting_to_dict():
    setting = Setting("key", "value")
    assert setting.to_dict() == {"key": "key", "value": "value"}
