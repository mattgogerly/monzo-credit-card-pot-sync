from app.models.account import AccountModel


def test_account_model_creation():
    account = AccountModel(
        type="test_type",
        access_token="test_access_token",
        refresh_token="test_refresh_token",
        token_expiry=1234567890,
        pot_id="test_pot_id",
    )
    # Without a joint account ID, the default should be None
    assert account.account_id is None
    assert account.type == "test_type"
    assert account.access_token == "test_access_token"
    assert account.refresh_token == "test_refresh_token"
    assert account.token_expiry == 1234567890
    assert account.pot_id == "test_pot_id"


def test_account_model_optional_account_id():
    account = AccountModel(
        type="test_type",
        access_token="test_access_token",
        refresh_token="test_refresh_token",
        token_expiry=1234567890,
        pot_id="test_pot_id",
        account_id="joint_123"
    )
    assert account.account_id == "joint_123"
    assert account.type == "test_type"
    assert account.access_token == "test_access_token"
    assert account.refresh_token == "test_refresh_token"
    assert account.token_expiry == 1234567890
    assert account.pot_id == "test_pot_id"
