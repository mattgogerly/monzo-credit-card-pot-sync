from enum import Enum


class Setting:
    def __init__(self, key, value):
        self.key = key
        self.value = value

    def to_dict(self) -> dict:
        return {"key": self.key, "value": self.value}


class SettingsPrefix(Enum):
    MONZO = "monzo"
    TRUELAYER = "truelayer"