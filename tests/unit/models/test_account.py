from app.models.account import AccountModel


def test_account_model_creation():
    account = AccountModel(
        type="test_type",
        access_token="test_access_token",
        refresh_token="test_refresh_token",
        token_expiry=1234567890,
        pot_id="test_pot_id",
    )
    assert account.type == "test_type"
    assert account.access_token == "test_access_token"
    assert account.refresh_token == "test_refresh_token"
    assert account.token_expiry == 1234567890
    assert account.pot_id == "test_pot_id"


def test_monzo_account_model_creation():
    account = AccountModel(
        type="Monzo",
        access_token="monzo_access_token",
        refresh_token="monzo_refresh_token",
        token_expiry=1234567890,
        pot_id="monzo_pot_id",
    )
    assert account.type == "Monzo"
    assert account.access_token == "monzo_access_token"
    assert account.refresh_token == "monzo_refresh_token"
    assert account.token_expiry == 1234567890
    assert account.pot_id == "monzo_pot_id"


def test_monzo_joint_account_model_creation():
    account = AccountModel(
        type="Monzo",
        access_token="monzo_joint_access_token",
        refresh_token="monzo_joint_refresh_token",
        token_expiry=1234567890,
        pot_id="monzo_joint_pot_id",
    )
    assert account.type == "Monzo"
    assert account.access_token == "monzo_joint_access_token"
    assert account.refresh_token == "monzo_joint_refresh_token"
    assert account.token_expiry == 1234567890
    assert account.pot_id == "monzo_joint_pot_id"