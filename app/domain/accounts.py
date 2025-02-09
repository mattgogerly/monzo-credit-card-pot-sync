import logging
from time import time
from urllib import parse

import requests as r

from app.domain.auth_providers import AuthProviderType, provider_mapping
from app.errors import AuthException

log = logging.getLogger("account")


class Account:
    def __init__(
        self,
        type,
        access_token=None,
        refresh_token=None,
        token_expiry=None,
        pot_id=None,
        account_id=None,  # Added optional account_id
    ):
        self.type = type
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.token_expiry = token_expiry
        self.pot_id = pot_id
        self.account_id = account_id
        self.auth_provider = provider_mapping[AuthProviderType(type)]

    def is_token_within_expiry_window(self):
        # returns True if the token expires in the next two minutes, or has already expired
        return self.token_expiry - int(time()) <= 120

    def refresh_access_token(self):
        log.info(f"{self.type} access token is within expiry window, refreshing tokens")

        try:
            tokens = self.auth_provider.refresh_access_token(self.refresh_token)
            self.access_token = tokens["access_token"]
            self.refresh_token = tokens["refresh_token"]
            self.token_expiry = int(time()) + tokens["expires_in"]

            log.info(
                f"Successfully refreshed {self.type} access token, new expiry time is {self.token_expiry}"
            )
        except KeyError as e:
            raise AuthException(e)
        except AuthException as e:
            log.error(f"Failed to refresh access token for {self.type}")
            raise e

    def get_auth_header(self):
        return {"Authorization": f"Bearer {self.access_token}"}


class MonzoAccount(Account):
    def __init__(
        self, access_token=None, refresh_token=None, token_expiry=None, pot_id=None, account_id=None
    ):
        super().__init__("Monzo", access_token, refresh_token, token_expiry, pot_id)
        # New: allow selected account_id (could be joint or personal)
        self.account_id = account_id

    def ping(self) -> None:
        r.get(
            f"{self.auth_provider.api_url}/ping/whoami", headers=self.get_auth_header()
        )

    def _fetch_accounts(self) -> list:
        response = r.get(
            f"{self.auth_provider.api_url}/accounts", headers=self.get_auth_header()
        )
        return response.json()["accounts"]

    def get_authorized_accounts(self) -> list:
        """Return a list of authorized accounts (personal & joint) with details."""
        return self._fetch_accounts()

    def get_account_id(self) -> str:
        """Return the selected account id. If none is set, default to the first account."""
        if self.account_id:
            return self.account_id
        accounts = self._fetch_accounts()
        if not accounts:
            raise AuthException("No accounts returned by Monzo API")
        self.account_id = accounts[0]["id"]
        return self.account_id

    def get_account_description(self) -> str:
        """Return the account description for the selected account."""
        selected = self.get_account_id()
        accounts = self._fetch_accounts()
        for account in accounts:
            if account["id"] == selected:
                return account.get("description", "")
        return ""

    def get_balance(self) -> int:
        query = parse.urlencode({"account_id": self.get_account_id()})
        response = r.get(
            f"{self.auth_provider.api_url}/balance?{query}",
            headers=self.get_auth_header(),
        )
        return response.json()["balance"]

    def get_pots(self) -> list[object]:
        query = parse.urlencode({"current_account_id": self.get_account_id()})
        response = r.get(
            f"{self.auth_provider.api_url}/pots?{query}", headers=self.get_auth_header()
        )
        pots = response.json()["pots"]
        return [p for p in pots if not p["deleted"]]

    def get_pot_balance(self, pot_id: str) -> int:
        pots = self.get_pots()
        pot = next(p for p in pots if p["id"] == pot_id)
        return pot["balance"]

    def add_to_pot(self, pot_id: str, amount: int) -> None:
        data = {
            "source_account_id": self.get_account_id(),
            "amount": amount,
            "dedupe_id": int(time()),
        }
        r.put(
            f"{self.auth_provider.api_url}/pots/{pot_id}/deposit",
            data=data,
            headers=self.get_auth_header(),
        )

    def withdraw_from_pot(self, pot_id: str, amount: int) -> None:
        data = {
            "destination_account_id": self.get_account_id(),
            "amount": amount,
            "dedupe_id": int(time()),
        }
        r.put(
            f"{self.auth_provider.api_url}/pots/{pot_id}/withdraw",
            data=data,
            headers=self.get_auth_header(),
        )

    def send_notification(self, title: str, message: str) -> None:
        body = {
            "account_id": self.get_account_id(),
            "type": "basic",
            "params[image_url]": "https://www.nyan.cat/cats/original.gif",
            "params[title]": title,
            "params[body]": message,
        }
        r.post(
            f"{self.auth_provider.api_url}/feed",
            data=body,
            headers=self.get_auth_header(),
        )


class TrueLayerAccount(Account):
    def __init__(
        self,
        type,
        access_token=None,
        refresh_token=None,
        token_expiry=None,
        pot_id=None,
        account_id=None  # Added optional account_id
    ):
        super().__init__(type, access_token, refresh_token, token_expiry, pot_id)
        self.account_id = account_id

    def ping(self) -> None:
        r.get(
            f"{self.auth_provider.api_url}/data/v1/me", headers=self.get_auth_header()
        )

    def get_cards(self) -> list[object]:
        response = r.get(
            f"{self.auth_provider.api_url}/data/v1/cards",
            headers=self.get_auth_header(),
        )
        return response.json()["results"]

    def get_card_balance(self, card_id: str) -> int:
        response = r.get(
            f"{self.auth_provider.api_url}/data/v1/cards/{card_id}/balance",
            headers=self.get_auth_header(),
        )
        return response.json()["results"][0]["current"]

    def get_total_balance(self) -> int:
        total_balance = 0
        cards = self.get_cards()
        for card in cards:
            card_id = card["account_id"]
            # multiply by 100 to get balance in minor units of currency
            total_balance += int(self.get_card_balance(card_id) * 100)
        return total_balance

