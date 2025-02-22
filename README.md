# Monzo Credit Card Pot Sync

![GitHub Release](https://img.shields.io/github/v/release/mattgogerly/monzo-credit-card-pot-sync?include_prereleases)
![GitHub Actions Workflow Status](https://img.shields.io/github/actions/workflow/status/mattgogerly/monzo-credit-card-pot-sync/build.yml?branch=main)
![Coveralls](https://img.shields.io/coverallsCoverage/github/mattgogerly/monzo-credit-card-pot-sync?branch=main)

This project provides a robust system to keep your Monzo pot in sync with your credit card spending. It allows you to spend on your credit cards day-to-day while ensuring there are always enough funds in your Monzo pot to pay off bills. The system supports multiple credit card providers and seamlessly manages both personal and joint Monzo accounts.

## Features

- **Automatic Fund Management:** Automatically deposits to or withdraws from your selected Monzo pot to match your credit card spending.
- **Flexible Pot Selection:** Easily choose and switch the designated Monzo pot that stays in sync.
- **Multiple Provider Support:** Connect various credit cards. Providers such as American Express and Barclaycard now include pending transaction calculations.
- **Joint Account Support:** Sync funds across both personal and joint Monzo accounts.
- **Cooldown & Override Logic:**  
  - **Normal Operations:**  
    - When you spend on a card, the pot is increased to match the new card balance.
    - If the pot balance exceeds your card balance, the excess is automatically withdrawn.
  - **Cooldown Scenario:**  
    - When the pot falls below the card balance with no new spending detected (perhaps due to a direct payment from the pot), a cooldown period is triggered.
    - Once the cooldown expires and if the card balance remains above the pot, the shortfall is deposited automatically.
  - **Override Spending:**  
    - If override spending is enabled while a cooldown is active and the card balance increases, the additional difference is deposited immediately.
    - The original shortfall remains under cooldown and will be addressed upon expiration.
- **Detailed Logging:** Every step—from token refreshes to pot adjustments and cooldown checks—is logged for visibility and troubleshooting.

## Extended Logic for Credit Card Providers

For cards like American Express and Barclaycard, pending transactions are now taken into account to calculate the true balance. This ensures the Monzo pot will adjust accurately to reflect your spending even when transactions are still pending.

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