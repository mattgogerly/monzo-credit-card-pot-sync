# Monzo Credit Card Pot Sync

![GitHub Release](https://img.shields.io/github/v/release/mattgogerly/monzo-credit-card-pot-sync?include_prereleases)
![GitHub Actions Workflow Status](https://img.shields.io/github/actions/workflow/status/mattgogerly/monzo-credit-card-pot-sync/build.yml?branch=main)
![Coveralls](https://img.shields.io/coverallsCoverage/github/mattgogerly/monzo-credit-card-pot-sync?branch=main)

This project is a tool to sync the balance of your credit cards and a Monzo pot. It allows you to use credit cards for your day-to-day spend, all the while ensuring your Monzo pot has enough funds to pay off bills in full — providing a seamless experience for managing your finances.

## Features

- Automatically add and remove funds from a Monzo pot as you spend on your credit cards
- Choose a Monzo pot to keep synced, and change it at any time
- Connect all of your credit card providers to keep your pot up to date
- **Support for joint Monzo accounts:** Seamlessly sync funds from both personal and joint accounts

### Extended Logic for Credit Card Providers
We've introduced enhanced processes for certain credit cards, such as American Express and Barclaycard, where pending transactions are considered. This ensures your Monzo pot always has enough funds to match your latest (including pending) card balance.

### Cooldown Logic
We employ a cooldown mechanism whenever the pot unexpectedly drops below the card balance without new spending. This logic applies to all configured credit accounts (including multiple cards) and works seamlessly with both personal and joint Monzo accounts.

There are four main scenarios:
1. Card balance increases (new spend): The pot is topped up to match the new card balance.  
2. Pot balance exceeds card balance: We withdraw the excess from the pot.  
3. Pot balance is below the card balance with no new spend (suspected direct pot payment):  
   - We trigger a cooldown period to wait for the final card balance to settle.  
   - If the cooldown expires but the card balance remains higher than the pot, the difference is deposited automatically.  
4. Override spending mode: If override is enabled and the card balance increases during cooldown, we still deposit the new difference immediately, leaving the original shortfall to be resolved once the cooldown ends.

Example:
1. Your card shows £200, pot has £100.  
2. Without new transactions, pot suddenly dips to £90 => triggers cooldown.  
3. During cooldown, you spend more => card goes to £110 => override logic deposits £20 to match that extra spend (bringing pot to £110).  
4. Cooldown stays active for the original shortfall. If, by cooldown’s end, the pot is still under the card balance, we deposit the difference.

## Installation

1. Clone the repository:
    ```bash
    git clone https://github.com/mattgogerly/monzo-credit-card-pot-sync.git
    ```
2. Navigate to the project directory:
    ```bash
    cd monzo-credit-card-pot-sync
    ```
3. Install Python dependencies:
    ```bash
    pip install -r requirements.txt
    ```
4. Install web dependencies:
    ```bash
    npm install
    ```
5. Build static web assets:
    ```bash
    npm run build-css
    ```

## Usage

1. Start the application:
    ```bash
    npm start
    ```
2. Open your browser and navigate to `http://localhost:1337`

## Configuration

1. Log in to the Monzo developer portal at `https://developers.monzo.com` (note you'll need to approve the login in the app)
2. Create a client, entering the redirect URL as `http://localhost:1337/auth/callback/monzo` and confidentiality as `Confidential`
3. Make a note of the client ID and client secret
4. Login to the TrueLayer console at `https://console.truelayer.com`
5. Create an application
6. Switch to the `Live` environment and add `http://localhost:1337/auth/callback/truelayer` as a redirect URI
7. Copy the client ID and client secret
8. Navigate to `http://localhost:1337/settings` and save the Monzo and TrueLayer client IDs and secrets
9. When prompted, accept the notification from Monzo to allow the application API access.

## Docker

Releases are also published as container images on GitHub Container Registry.

1. Start the container:
   ```bash
   docker compose up -d
   ```

### Using a Reverse Proxy

If you are using a reverse proxy, set the environment variable `POT_SYNC_LOCAL_URL` in your Docker Compose file or Docker run command to the external URL of your application. For example:

```yaml
environment:
  - POT_SYNC_LOCAL_URL=https://subdomain.fulldomain.com
```

When setting up Monzo or TrueLayer redirect URLs, use the URL that was set in the `POT_SYNC_LOCAL_URL` variable to enable the accounts to successfully link.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Contact

For any questions or feedback, please open an issue on GitHub.