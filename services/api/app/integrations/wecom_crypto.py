from __future__ import annotations

import base64
import hashlib
import hmac
import struct
from dataclasses import dataclass
from xml.etree import ElementTree

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


class WeComCryptoError(ValueError):
    """A deliberately non-specific callback authentication/decryption error."""


@dataclass(frozen=True, slots=True)
class WeComDecryptedMessage:
    xml: bytes
    fields: dict[str, str]


class WeComCallbackCrypto:
    """Verify and decrypt WeCom safe-mode callback payloads."""

    _PADDING_BLOCK_SIZE = 32

    def __init__(self, *, token: str, encoding_aes_key: str, corp_id: str) -> None:
        normalized_token = token.strip()
        normalized_key = encoding_aes_key.strip()
        normalized_corp_id = corp_id.strip()
        if not normalized_token or not normalized_corp_id or len(normalized_key) != 43:
            raise WeComCryptoError("invalid callback configuration")
        try:
            key = base64.b64decode(f"{normalized_key}=", validate=True)
        except (ValueError, TypeError) as exc:
            raise WeComCryptoError("invalid callback configuration") from exc
        if len(key) != 32:
            raise WeComCryptoError("invalid callback configuration")
        self._token = normalized_token
        self._key = key
        self._corp_id = normalized_corp_id.encode("utf-8")

    def decrypt(
        self,
        *,
        encrypted: str,
        signature: str,
        timestamp: str,
        nonce: str,
    ) -> WeComDecryptedMessage:
        xml = self.decrypt_raw(
            encrypted=encrypted,
            signature=signature,
            timestamp=timestamp,
            nonce=nonce,
        )
        return WeComDecryptedMessage(xml=xml, fields=parse_wecom_xml(xml))

    def decrypt_raw(
        self,
        *,
        encrypted: str,
        signature: str,
        timestamp: str,
        nonce: str,
    ) -> bytes:
        self._verify_signature(
            encrypted=encrypted,
            signature=signature,
            timestamp=timestamp,
            nonce=nonce,
        )
        try:
            encrypted_bytes = base64.b64decode(encrypted, validate=True)
        except (ValueError, TypeError) as exc:
            raise WeComCryptoError("invalid callback payload") from exc
        if not encrypted_bytes or len(encrypted_bytes) % 16:
            raise WeComCryptoError("invalid callback payload")
        decryptor = Cipher(
            algorithms.AES(self._key),
            modes.CBC(self._key[:16]),
        ).decryptor()
        padded = decryptor.update(encrypted_bytes) + decryptor.finalize()
        plaintext = self._unpad(padded)
        if len(plaintext) < 20:
            raise WeComCryptoError("invalid callback payload")
        message_length = struct.unpack("!I", plaintext[16:20])[0]
        message_end = 20 + message_length
        if message_length == 0 or message_end > len(plaintext):
            raise WeComCryptoError("invalid callback payload")
        xml = plaintext[20:message_end]
        receiver_id = plaintext[message_end:]
        if not hmac.compare_digest(receiver_id, self._corp_id):
            raise WeComCryptoError("invalid callback payload")
        return xml

    def _verify_signature(
        self,
        *,
        encrypted: str,
        signature: str,
        timestamp: str,
        nonce: str,
    ) -> None:
        if (
            not encrypted
            or not signature
            or not timestamp.isdigit()
            or not nonce
            or len(timestamp) > 20
            or len(nonce) > 256
        ):
            raise WeComCryptoError("invalid callback signature")
        digest = hashlib.sha1(  # noqa: S324 - mandated by the WeCom protocol
            "".join(sorted((self._token, timestamp, nonce, encrypted))).encode("utf-8")
        ).hexdigest()
        if not hmac.compare_digest(digest, signature.casefold()):
            raise WeComCryptoError("invalid callback signature")

    def _unpad(self, value: bytes) -> bytes:
        if not value:
            raise WeComCryptoError("invalid callback payload")
        padding = value[-1]
        if padding < 1 or padding > self._PADDING_BLOCK_SIZE:
            raise WeComCryptoError("invalid callback payload")
        if not hmac.compare_digest(value[-padding:], bytes((padding,)) * padding):
            raise WeComCryptoError("invalid callback payload")
        return value[:-padding]


def parse_wecom_xml(value: bytes) -> dict[str, str]:
    if not value or len(value) > 1_048_576:
        raise WeComCryptoError("invalid callback payload")
    uppercase = value.upper()
    if b"<!DOCTYPE" in uppercase or b"<!ENTITY" in uppercase:
        raise WeComCryptoError("invalid callback payload")
    try:
        root = ElementTree.fromstring(value)  # noqa: S314 - DTD/entity declarations rejected
    except ElementTree.ParseError as exc:
        raise WeComCryptoError("invalid callback payload") from exc
    if root.tag != "xml":
        raise WeComCryptoError("invalid callback payload")
    fields: dict[str, str] = {}
    for child in root:
        if len(fields) >= 100 or len(child):
            raise WeComCryptoError("invalid callback payload")
        if child.tag and child.text is not None:
            fields[child.tag] = child.text.strip()
    return fields


def extract_encrypted_xml(value: bytes) -> str:
    fields = parse_wecom_xml(value)
    encrypted = fields.get("Encrypt")
    if not encrypted:
        raise WeComCryptoError("invalid callback payload")
    return encrypted


__all__ = [
    "WeComCallbackCrypto",
    "WeComCryptoError",
    "WeComDecryptedMessage",
    "extract_encrypted_xml",
    "parse_wecom_xml",
]
