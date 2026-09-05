from datetime import timedelta
from utils.security import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
)


def test_password_hashing():
    raw_password = "mySecretPassword123!"
    hashed = hash_password(raw_password)

    assert hashed != raw_password
    assert verify_password(raw_password, hashed) is True
    assert verify_password("wrong_password", hashed) is False


def test_jwt_token_encode_decode():
    payload_data = {"sub": "42", "email": "test@example.com"}
    token = create_access_token(payload_data)

    decoded = decode_access_token(token)
    assert decoded is not None
    assert decoded.get("sub") == "42"
    assert decoded.get("email") == "test@example.com"
    assert "exp" in decoded


def test_jwt_token_expired():
    payload_data = {"sub": "42"}
    # Create an already-expired token (-1 minute)
    token = create_access_token(payload_data, expires_delta=timedelta(minutes=-1))

    decoded = decode_access_token(token)
    assert decoded is None


def test_jwt_token_invalid():
    invalid_token = "not.a.valid.jwt.token"
    decoded = decode_access_token(invalid_token)
    assert decoded is None
