from services.auth import create_access_token, decode_access_token


def test_access_token_contains_user_identity():
    token = create_access_token(
        user_id=123,
        role="owner",
    )

    payload = decode_access_token(token)

    assert payload["sub"] == "123"
    assert payload["role"] == "owner"


def test_invalid_token_is_rejected():
    try:
        decode_access_token("this-is-not-a-valid-token")
    except Exception:
        pass
    else:
        assert False, "Invalid token should be rejected"