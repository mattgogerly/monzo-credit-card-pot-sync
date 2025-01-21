import logging
from enum import Enum
from time import time
from urllib import parse

import requests as r

from app.config import Config
from app.domain.settings import SettingsPrefix
from app.errors import AuthException
from app.extensions import db
from app.models.setting_repository import SqlAlchemySettingRepository

log = logging.getLogger("auth_providers")

repository = SqlAlchemySettingRepository(db)


class AuthProviderType(Enum):
    MONZO = "Monzo"
    AMEX = "American Express"
    BARCLAYCARD = "Barclaycard"
    HALIFAX = "Halifax"
    NATWEST = "NatWest"


class AuthProvider:
    def __init__(
        self,
        name,
        type,
        icon_name,
        api_url,
        auth_url,
        token_url,
        token_endpoint,
        oauth_scopes,
        callback_url,
        setting_prefix,
    ):
        self.name = name
        self.type = type
        self.icon_name = icon_name
        self.api_url = api_url
        self.auth_url = auth_url
        self.token_url = token_url
        self.token_endpoint = token_endpoint
        self.oauth_scopes = oauth_scopes
        self.callback_url = callback_url
        self.setting_prefix = setting_prefix

    def get_default_oauth_request_params(self):
        return {
            "client_id": repository.get(f"{self.setting_prefix}_client_id"),
            "response_type": "code",
            "redirect_uri": self.callback_url,
            "state": f"{self.type}-{int(time())}",
        }

    @staticmethod
    def get_provider_specific_oauth_request_params() -> dict:
        return {}

    def create_oauth_request_url(self) -> str:
        params = (
            self.get_default_oauth_request_params()
            | self.get_provider_specific_oauth_request_params()
        )
        params = parse.urlencode(params)
        return f"{self.auth_url}?{params}"

    def get_oauth_token_request_body(self, code) -> dict:
        return {
            "client_id": repository.get(f"{self.setting_prefix}_client_id"),
            "client_secret": repository.get(f"{self.setting_prefix}_client_secret"),
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": self.callback_url,
        }

    def get_token_url(self):
        return f"{self.token_url}{self.token_endpoint}"

    def handle_oauth_code_callback(self, code) -> dict:
        try:
            log.info(
                f"Received OAuth callback for {self.type}, exchanging for access token"
            )
            body = self.get_oauth_token_request_body(code)
            response = r.post(self.get_token_url(), data=body)
            return response.json()
        except (KeyError, r.exceptions.JSONDecodeError):
            log.error(
                f"No access token in token exchange response body for {self.type}"
            )
            raise AuthException("No access token returned")

    def get_refresh_request_body(self, refresh_token: str) -> dict:
        return {
            "client_id": repository.get(f"{self.setting_prefix}_client_id"),
            "client_secret": repository.get(f"{self.setting_prefix}_client_secret"),
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }

    def refresh_access_token(self, refresh_token: str) -> dict:
        try:
            log.info(f"Refreshing tokens for {self.type}")
            body = self.get_refresh_request_body(refresh_token)
            response = r.post(f"{self.token_url}{self.token_endpoint}", data=body)
            return response.json()
        except (KeyError, r.exceptions.JSONDecodeError):
            log.error(
                f"No access token in refresh tokens response body for {self.type}"
            )
            raise AuthException("No access token returned")


class MonzoAuthProvider(AuthProvider):
    def __init__(self):
        super().__init__(
            "Monzo",
            AuthProviderType.MONZO.value,
            "monzo.svg",
            "https://api.monzo.com",
            "https://auth.monzo.com",
            "https://api.monzo.com",
            "/oauth2/token",
            "",
            f"{Config.LOCAL_URL}/auth/callback/monzo",
            SettingsPrefix.MONZO.value,
        )

    def get_provider_specific_oauth_request_params(self) -> dict:
        return {"response_mode": "form_post"}


class TrueLayerAuthProvider(AuthProvider):
    def __init__(self, name, type, icon_name):
        super().__init__(
            name,
            type,
            icon_name,
            "https://api.truelayer.com",
            "https://auth.truelayer.com",
            "https://auth.truelayer.com",
            "/connect/token",
            "accounts balance cards offline_access",
            f"{Config.LOCAL_URL}/auth/callback/truelayer",
            SettingsPrefix.TRUELAYER.value,
        )


class AmericanExpressAuthProvider(TrueLayerAuthProvider):
    def __init__(self):
        super().__init__("American Express", AuthProviderType.AMEX.value, "amex.svg")

    def get_provider_specific_oauth_request_params(self) -> dict:
        return {"providers": "uk-ob-amex", "scope": self.oauth_scopes}


class BarclaycardAuthProvider(TrueLayerAuthProvider):
    def __init__(self):
        super().__init__(
            "Barclaycard", AuthProviderType.BARCLAYCARD.value, "barclaycard.svg"
        )

    def get_provider_specific_oauth_request_params(self) -> dict:
        return {"providers": "uk-ob-barclaycard", "scope": self.oauth_scopes}


class HalifaxAuthProvider(TrueLayerAuthProvider):
    def __init__(self):
        super().__init__("Halifax", AuthProviderType.HALIFAX.value, "halifax.svg")

    def get_provider_specific_oauth_request_params(self) -> dict:
        return {"providers": "uk-ob-halifax", "scope": self.oauth_scopes}


class NatWestAuthProvider(TrueLayerAuthProvider):
    def __init__(self):
        super().__init__("NatWest", AuthProviderType.NATWEST.value, "natwest.svg")

    def get_provider_specific_oauth_request_params(self) -> dict:
        return {"providers": "uk-ob-natwest", "scope": self.oauth_scopes}


provider_mapping: dict[AuthProviderType, AuthProvider] = {
    AuthProviderType.MONZO: MonzoAuthProvider(),
    AuthProviderType.AMEX: AmericanExpressAuthProvider(),
    AuthProviderType.BARCLAYCARD: BarclaycardAuthProvider(),
    AuthProviderType.HALIFAX: HalifaxAuthProvider(),
    AuthProviderType.NATWEST: NatWestAuthProvider(),
}
