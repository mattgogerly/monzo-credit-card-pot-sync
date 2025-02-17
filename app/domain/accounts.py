import logging
import math
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
        cooldown_until=None,  # existing field for cooldown
        prev_balance: int = 0  # new field, defaulting to 0
    ):
        self.type = type
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.token_expiry = token_expiry
        self.pot_id = pot_id
        self.account_id = account_id
        self.auth_provider = provider_mapping[AuthProviderType(type)]
        self.cooldown_until = cooldown_until
        self.prev_balance = prev_balance  # persist previous pot balance

    def is_token_within_expiry_window(self):
        # Returns True if the token expires in the next two minutes or has already expired.
        return self.token_expiry - int(time()) <= 120

    def refresh_access_token(self):
        log.info(f"{self.type} access token is within expiry window, refreshing tokens")
        try:
            tokens = self.auth_provider.refresh_access_token(self.refresh_token)

            # Log response safely (hiding tokens)
            sanitized_tokens = {k: "***REDACTED***" if "token" in k else v for k, v in tokens.items()}
            log.debug(f"{self.type} token refresh response: {sanitized_tokens}")

            # Validate expected fields
            if "access_token" not in tokens or "refresh_token" not in tokens:
                log.error(f"{self.type} token refresh response missing fields: {sanitized_tokens}")
                raise AuthException("Access token refresh response missing required fields")

            # Assign new tokens
            self.access_token = tokens["access_token"]
            self.refresh_token = tokens["refresh_token"]
            self.token_expiry = int(time()) + tokens["expires_in"]

            log.info(f"Successfully refreshed {self.type} access token, new expiry time is {self.token_expiry}")

        except KeyError as e:
            log.error(f"KeyError while refreshing {self.type} token: {str(e)} - Response: {sanitized_tokens}")
            raise AuthException("Unexpected token response format") from e

        except AuthException as e:
            log.error(f"Failed to refresh access token for {self.type}")
            raise e

    def get_auth_header(self):
        return {"Authorization": f"Bearer {self.access_token}"}

    def pre_deposit_check(self, current_balance, new_balance, cooldown_duration):
        """
        Checks before a deposit:
         - If performing the deposit (resulting in new_balance) would be lower than current_balance
           then a cooldown period is applied.
         - Returns True if deposit is allowed, otherwise False.
          
        Parameters:
          current_balance: the current balance before deposit.
          new_balance: the prospective balance after deposit.
          cooldown_duration: the desired cooldown period (in seconds) from settings.
        """
        now = int(time())
        if new_balance < current_balance:
            if self.cooldown_until and now < self.cooldown_until:
                log.info(f"Cooldown active until {self.cooldown_until}. Deposit postponed for {self.type}.")
                return False
            else:
                # Initiate cooldown period before allowing deposit
                self.cooldown_until = now + cooldown_duration
                log.info(
                    f"Withdrawal would reduce balance for {self.type}. Initiating a cooldown until {self.cooldown_until}."
                )
                return False
        return True


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
    def __init__(self, type, access_token=None, refresh_token=None, token_expiry=None, pot_id=None, account_id=None):
        super().__init__(type, access_token, refresh_token, token_expiry, pot_id, account_id)

    def ping(self) -> None:
        r.get(f"{self.auth_provider.api_url}/data/v1/me", headers=self.get_auth_header())

    def get_cards(self) -> list:
        response = r.get(f"{self.auth_provider.api_url}/data/v1/cards", headers=self.get_auth_header())
        response.raise_for_status()
        return response.json()["results"]

    def get_card_balance(self, card_id: str) -> float:
        response = r.get(f"{self.auth_provider.api_url}/data/v1/cards/{card_id}/balance", headers=self.get_auth_header())
        response.raise_for_status()
        data = response.json()["results"][0]
        # Multiply by 100, round up, then divide by 100 to get two decimal places
        return math.ceil(data["current"] * 100) / 100

    def get_pending_transactions(self, card_id: str) -> list:
        response = r.get(f"{self.auth_provider.api_url}/data/v1/cards/{card_id}/transactions/pending", headers=self.get_auth_header())
        response.raise_for_status()
        transactions = response.json()["results"]
        # Multiply by 100, round up, then divide by 100 to get two decimal places
        return [math.ceil(txn["amount"] * 100) / 100 for txn in transactions] if transactions else []

    def get_total_balance(self) -> int:
        total_balance = 0.0
        cards = self.get_cards()

        for card in cards:
            card_id = card["account_id"]
            balance = self.get_card_balance(card_id)
            provider = card.get("provider", {}).get("display_name")

            if provider in ["AMEX"]:
                pending_transactions = self.get_pending_transactions(card_id)

                # Separate charges and payments/refunds
                pending_charges = math.ceil(sum(txn for txn in pending_transactions if txn > 0) * 100) / 100
                pending_payments = math.ceil(sum(txn for txn in pending_transactions if txn < 0) * 100) / 100

                # it looks like pending charges might take into account credits
                pending_balance = pending_charges # + pending_payments

                adjusted_balance = balance + pending_balance

                log.info(f"Current Balance (Excluding Pending Transactions): £{balance:.2f}")
                log.info(f"Pending Charges: £{pending_charges:.2f}")
                log.info(f"Pending Payments: £{pending_payments:.2f}")
                log.info(f"Pending Balance: £{pending_balance:.2f}")
                log.info(f"Total Balance: £{adjusted_balance:.2f}")

                balance = adjusted_balance

            if provider in ["BARCLAYCARD"]:
                pending_transactions = self.get_pending_transactions(card_id)

                # Separate charges and payments/refunds
                pending_charges = math.ceil(sum(txn for txn in pending_transactions if txn > 0) * 100) / 100
                pending_payments = math.ceil(sum(txn for txn in pending_transactions if txn < 0) * 100) / 100

                # it looks like pending charges might take into account credits
                pending_balance = pending_charges # + pending_payments

                # barclaycard seem to add pending charges to the balance instantly, so we ignore pending transactions
                adjusted_balance = balance

                log.info(f"Current Balance (Excluding Pending Transactions): £{balance:.2f}")
                log.info(f"Pending Charges: £{pending_charges:.2f}")
                log.info(f"Pending Payments: £{pending_payments:.2f}")
                log.info(f"Pending Balance: £{pending_balance:.2f}")
                log.info(f"Total Balance: £{adjusted_balance:.2f}")

                balance = adjusted_balance

            total_balance += balance

        log.info(f"Total balance calculated: £{total_balance:.2f}")
        return int(total_balance * 100)  # Convert balance to pence