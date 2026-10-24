"""CryptoJS-compatible AES helpers.

The Sijilat web page encrypts some request bodies in the browser with
``CryptoJS.AES.encrypt(text, passphrase).toString()``. With a *string*
passphrase, CryptoJS uses the OpenSSL "Salted__" format:

    base64( b"Salted__" + 8-byte salt + AES-256-CBC ciphertext )

where key and IV come from OpenSSL's EVP_BytesToKey (MD5, one iteration)
and the plaintext uses PKCS7 padding.

This module only does that. It knows nothing about HTTP or Sijilat.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import os

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

_MAGIC = b"Salted__"
_SALT_LEN = 8
_KEY_LEN = 32  # AES-256
_IV_LEN = 16


class CryptoError(ValueError):
    """Raised when data cannot be encrypted or decrypted."""


def evp_bytes_to_key(passphrase: bytes, salt: bytes) -> tuple[bytes, bytes]:
    """Derive (key, iv) like OpenSSL EVP_BytesToKey with MD5 and count=1."""
    derived = b""
    block = b""
    while len(derived) < _KEY_LEN + _IV_LEN:
        block = hashlib.md5(block + passphrase + salt).digest()
        derived += block
    return derived[:_KEY_LEN], derived[_KEY_LEN:_KEY_LEN + _IV_LEN]


def encrypt_cryptojs(plaintext: str, passphrase: str, salt: bytes | None = None) -> str:
    """Encrypt text the way CryptoJS does. ``salt`` is random unless given (tests)."""
    if salt is None:
        salt = os.urandom(_SALT_LEN)
    if len(salt) != _SALT_LEN:
        raise CryptoError(f"salt must be {_SALT_LEN} bytes")
    key, iv = evp_bytes_to_key(passphrase.encode("utf-8"), salt)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    body = cipher.encrypt(pad(plaintext.encode("utf-8"), AES.block_size))
    return base64.b64encode(_MAGIC + salt + body).decode("ascii")


def decrypt_cryptojs(token: str, passphrase: str) -> str:
    """Decrypt a CryptoJS/OpenSSL "Salted__" base64 string.

    Raises CryptoError for bad base64, a missing header, bad padding or
    output that is not UTF-8. A wrong passphrase is caught this way almost
    always, but not with certainty (about 1 in 256 wrong keys give valid
    padding), so callers should also check that the result parses as JSON.
    """
    try:
        raw = base64.b64decode(token.strip(), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise CryptoError("input is not valid base64") from exc

    if not raw.startswith(_MAGIC):
        raise CryptoError("missing 'Salted__' header")
    if len(raw) < len(_MAGIC) + _SALT_LEN + AES.block_size:
        raise CryptoError("input too short")

    salt = raw[len(_MAGIC):len(_MAGIC) + _SALT_LEN]
    body = raw[len(_MAGIC) + _SALT_LEN:]
    if len(body) % AES.block_size != 0:
        raise CryptoError("ciphertext length is not a multiple of the block size")

    key, iv = evp_bytes_to_key(passphrase.encode("utf-8"), salt)
    try:
        padded = AES.new(key, AES.MODE_CBC, iv).decrypt(body)
        return unpad(padded, AES.block_size).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise CryptoError("decryption failed (wrong passphrase or corrupted data)") from exc
