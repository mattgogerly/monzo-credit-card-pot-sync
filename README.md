# Monzo Credit Card Pot Sync

![GitHub Release](https://img.shields.io/github/v/release/mattgogerly/monzo-credit-card-pot-sync?include_prereleases)
![GitHub Actions Workflow Status](https://img.shields.io/github/actions/workflow/status/mattgogerly/monzo-credit-card-pot-sync/build.yml?branch=main)
![Coveralls](https://img.shields.io/coverallsCoverage/github/mattgogerly/monzo-credit-card-pot-sync?branch=main)

This project is a tool to sync the balance of your credit cards and a Monzo pot. It allows you to use credit cards for your day-to-day spend, all the while ensuring your Monzo pot has enough funds to pay off bills in full - providing a seamless experience for managing your finances.

## Features

- Automatically add and remove funds from a Monzo pot as you spend on your credit cards
- Choose a Monzo pot to keep synced, and change it at any time
- Connect all of your credit card providers to keep your pot up to date

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
8. Navigate to `https://localhost:1337/settings` and save the Monzo and TrueLayer client IDs and secrets

You're all set! Head to `https://localhost:1337/accounts` to connect your Monzo account and credit cards.

## Docker

Releases are also published as container images on GitHub Container Registry.

1. Start the container:
   ```bash
   docker compose up -d
   ```
2. Open your browser and navigate to `http://localhost:1337`

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Contact

For any questions or feedback, please open an issue on GitHub.
