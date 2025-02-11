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
        account_id=None,
    ):
        self.type = type
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.token_expiry = token_expiry
        self.pot_id = pot_id
        self.account_id = account_id
        self.auth_provider = provider_mapping[AuthProviderType(type)]

    def is_token_within_expiry_window(self):
        # Returns True if the token expires in the next two minutes or has already expired.
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
        # Pass all parameters directly to the parent class
        super().__init__("Monzo", access_token, refresh_token, token_expiry, pot_id, account_id)

    def ping(self) -> None:
        r.get(
            f"{self.auth_provider.api_url}/ping/whoami", headers=self.get_auth_header()
        )

    def _fetch_accounts(self) -> list:
        response = r.get(
            f"{self.auth_provider.api_url}/accounts", headers=self.get_auth_header()
        )
        response.raise_for_status()
        return response.json()["accounts"]

    def get_authorized_accounts(self) -> list:
        """Return a list of authorized accounts (both personal and joint) with details."""
        return self._fetch_accounts()

    def get_account_id(self, account_selection="personal") -> str:
        """
        Return the account id for the desired account type.
        Defaults to personal ('uk_retail') and uses 'uk_retail_joint' for joint accounts.
        """
        desired_type = "uk_retail_joint" if account_selection == "joint" else "uk_retail"
        accounts = self._fetch_accounts()
        for account in accounts:
            if account["type"] == desired_type:
                return account["id"]
        raise AuthException(f"No account found for type: {desired_type}")

    def get_account_description(self, account_selection="personal") -> str:
        """Return the account description for the selected account."""
        desired_id = self.get_account_id(account_selection=account_selection)
        accounts = self._fetch_accounts()
        for account in accounts:
            if account["id"] == desired_id:
                return account.get("description", "")
        return ""

    def get_balance(self, account_selection="personal") -> int:
        """
        Retrieve the balance for the specified account type.
        :param account_selection: 'personal' for personal account, 'joint' for joint account.
        :return: Balance in minor units (e.g., pence for GBP).
        """
        account_id = self.get_account_id(account_selection=account_selection)
        query = parse.urlencode({"account_id": account_id})
        response = r.get(
            f"{self.auth_provider.api_url}/balance?{query}",
            headers=self.get_auth_header(),
        )
        response.raise_for_status()  # Raise an exception for HTTP errors
        return response.json()["balance"]

    def get_pots(self, account_selection="personal") -> list:
        """
        Get pots based on the selected account type.
        By default, uses the personal account; for joint, pass account_selection="joint".
        """
        current_account_id = self.get_account_id(account_selection)
        query = parse.urlencode({"current_account_id": current_account_id})
        response = r.get(
            f"{self.auth_provider.api_url}/pots?{query}", headers=self.get_auth_header()
        )
        response.raise_for_status()
        pots = response.json()["pots"]
        return [p for p in pots if not p["deleted"]]

    def get_pot_balance(self, pot_id: str) -> int:
        # Try personal account first, then fallback to joint account if needed.
        for account_selection in ("personal", "joint"):
            pots = self.get_pots(account_selection)
            pot = next((p for p in pots if p["id"] == pot_id), None)
            if pot is not None:
                return pot["balance"]
        raise Exception(f"Pot with id {pot_id} not found in personal or joint pots.")

    def get_account_type(self, pot_id: str) -> str:
        """
        Retrieve the account type (personal or joint) for the given pot ID.
        """
        for account_selection in ("personal", "joint"):
            pots = self.get_pots(account_selection)
            if any(p["id"] == pot_id for p in pots):
                return account_selection
        raise Exception(f"Pot with id {pot_id} not found in personal or joint pots.")

    def add_to_pot(self, pot_id: str, amount: int, account_selection="personal") -> None:
        data = {
            "source_account_id": self.get_account_id(account_selection=account_selection),
            "amount": amount,
            "dedupe_id": str(int(time())),  # Ensure dedupe_id is a string
        }
        response = r.put(
            f"{self.auth_provider.api_url}/pots/{pot_id}/deposit",
            data=data,
            headers=self.get_auth_header(),
        )
        if response.status_code != 200:
            log.error(f"Failed to deposit to pot: {response.json()}")
            raise Exception(f"Deposit failed: {response.json()}")

    def withdraw_from_pot(self, pot_id: str, amount: int, account_selection="personal") -> None:
        data = {
            "destination_account_id": self.get_account_id(account_selection=account_selection),
            "amount": amount,
            "dedupe_id": str(int(time())),  # Ensure dedupe_id is a string
        }
        response = r.put(
            f"{self.auth_provider.api_url}/pots/{pot_id}/withdraw",
            data=data,
            headers=self.get_auth_header(),
        )
        if response.status_code != 200:
            log.error(f"Failed to withdraw from pot: {response.json()}")
            raise Exception(f"Withdrawal failed: {response.json()}")

    def send_notification(self, title: str, message: str, account_selection="personal") -> None:
        body = {
            "account_id": self.get_account_id(account_selection=account_selection),
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
        account_id=None,
    ):
        super().__init__(type, access_token, refresh_token, token_expiry, pot_id, account_id)

    def ping(self) -> None:
        r.get(
            f"{self.auth_provider.api_url}/data/v1/me", headers=self.get_auth_header()
        )

    def get_cards(self) -> list:
        response = r.get(
            f"{self.auth_provider.api_url}/data/v1/cards",
            headers=self.get_auth_header(),
        )
        response.raise_for_status()
        return response.json()["results"]

    def get_card_balance(self, card_id: str) -> int:
        # Fetch card balance
        response = r.get(
            f"{self.auth_provider.api_url}/data/v1/cards/{card_id}/balance",
            headers=self.get_auth_header(),
        )
        response.raise_for_status()
        data = response.json()["results"][0]

        log.info(f"Full JSON response for card {card_id} balance: {data}")

        credit_limit = data.get("credit_limit")
        available = data.get("available")
        current_balance = data.get("current")

        if credit_limit is not None and available is not None:
            true_balance = int((credit_limit - available) * 100)
        elif current_balance is not None:
            true_balance = int(current_balance * 100)
            log.warning(f"Using 'current' balance for card {card_id} due to missing 'credit_limit' or 'available'")
        else:
            log.error(f"Missing balance data for card {card_id}: {data}")
            raise KeyError(f"Missing balance fields in response: {data}")

        # Fetch pending transactions
        url = f"{self.auth_provider.api_url}/data/v1/cards/{card_id}/transactions/pending"
        headers = self.get_auth_header()
        log.info(f"Fetching pending transactions from {url} with headers {headers}")
        response = r.get(url, headers=headers)
        log.info(f"Response status code: {response.status_code}")
        log.info(f"Response content: {response.content}")

        if response.status_code == 403:
            log.warning("403 Forbidden error retrieving pending transactions. Using 0 as a fallback.")
            pending_balance = 0
        else:
            response.raise_for_status()
            try:
                pending_transactions = response.json().get("results", [])
                log.info(f"Full JSON response for pending transactions: {pending_transactions}")
            except ValueError:
                pending_transactions = []
            pending_balance = sum(txn["amount"] for txn in pending_transactions)

        return true_balance + pending_balance

    def get_total_balance(self) -> int:
        total_balance = 0
        cards = self.get_cards()
        for card in cards:
            card_id = card["account_id"]
            total_balance += self.get_card_balance(card_id)
        return total_balance