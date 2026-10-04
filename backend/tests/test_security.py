"""Security helper tests: password hashing + JWT access/refresh tokens."""
import pytest

from app.security import (decode_token, hash_pw, hash_token, make_access, make_refresh,
                          new_jti, verify_pw)


def test_password_hash_roundtrip():
    h = hash_pw("Str0ng!Pass")
    assert h != "Str0ng!Pass"
    assert verify_pw("Str0ng!Pass", h)
    assert not verify_pw("wrong", h)


def test_verify_bad_hash_is_false():
    assert verify_pw("x", "not-a-hash") is False


def test_access_token_claims():
    tok = make_access("user123", "client")
    claims = decode_token(tok)
    assert claims["sub"] == "user123"
    assert claims["role"] == "client"
    assert claims["typ"] == "access"
    assert "jti" in claims


def test_refresh_token_typed():
    jti = new_jti()
    tok = make_refresh("user123", jti)
    claims = decode_token(tok)
    assert claims["typ"] == "refresh"
    assert claims["jti"] == jti


def test_tampered_token_rejected():
    tok = make_access("user123", "client")
    with pytest.raises(Exception):
        decode_token(tok + "tamper")


def test_token_hash_is_stable_and_opaque():
    assert hash_token("abc") == hash_token("abc")
    assert hash_token("abc") != "abc"
