from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_hash_roundtrip():
    h = hash_password("a-long-password")
    assert h != "a-long-password"
    assert verify_password("a-long-password", h)
    assert not verify_password("wrong-password", h)


def test_verify_password_handles_garbage_hash():
    assert not verify_password("whatever", "not-a-hash")


def test_token_roundtrip():
    token = create_access_token("user-123")
    assert decode_access_token(token) == "user-123"


def test_garbage_token_rejected():
    assert decode_access_token("garbage") is None
