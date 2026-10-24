"""CryptoJS-compatible AES: round trip, OpenSSL header, bad input."""
import pytest

from sijilat.crypto import CryptoError, decrypt_cryptojs, encrypt_cryptojs


def test_round_trip_with_arabic():
    text = '{"cr_no": "931", "name": "مجوهرات اسيا"}'
    assert decrypt_cryptojs(encrypt_cryptojs(text, "pass"), "pass") == text


def test_output_has_openssl_salted_header():
    assert encrypt_cryptojs("x", "pass").startswith("U2FsdGVkX1")   # base64 of "Salted__"


def test_bad_input_raises():
    with pytest.raises(CryptoError):
        decrypt_cryptojs("not base64!!", "pass")
