from __future__ import annotations

import base64
import hashlib
import os
import uuid
from datetime import UTC, datetime

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.serialization import pkcs12


class CertificateError(ValueError):
    """Certificado invalido ou senha incorreta."""


def _key() -> AESGCM:
    raw = os.environ.get("STK_CERT_ENCRYPTION_KEY")
    if not raw:
        raise CertificateError("STK_CERT_ENCRYPTION_KEY nao configurada")
    return AESGCM(base64.b64decode(raw))


def encrypt(data: bytes) -> tuple[bytes, bytes]:
    nonce = os.urandom(12)
    return _key().encrypt(nonce, data, None), nonce


def decrypt(ciphertext: bytes, nonce: bytes) -> bytes:
    return _key().decrypt(nonce, ciphertext, None)


def inspect_pfx(content: bytes, password: str) -> dict[str, object]:
    try:
        private_key, certificate, _chain = pkcs12.load_key_and_certificates(
            content, password.encode()
        )
    except Exception as error:
        raise CertificateError(
            "Nao foi possivel abrir o .pfx com a senha informada"
        ) from error
    if private_key is None or certificate is None:
        raise CertificateError("O arquivo nao contem chave privada e certificado")
    return {
        "subject_name": certificate.subject.rfc4514_string(),
        "not_valid_before": certificate.not_valid_before_utc,
        "not_valid_after": certificate.not_valid_after_utc,
        "thumbprint_sha256": hashlib.sha256(content).hexdigest(),
        "expired": certificate.not_valid_after_utc < datetime.now(UTC),
    }


def load_pem_pair(content: bytes, password: str) -> tuple[bytes, bytes]:
    private_key, certificate, _chain = pkcs12.load_key_and_certificates(
        content, password.encode()
    )
    cert_pem = certificate.public_bytes(serialization.Encoding.PEM)  # type: ignore[union-attr]
    key_pem = private_key.private_bytes(  # type: ignore[union-attr]
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return cert_pem, key_pem


def new_key_id(establishment_id: uuid.UUID, environment: str) -> str:
    return f"est-{establishment_id.hex[:12]}-{environment}"


def ssl_context_from_pfx(content: bytes, password: str) -> "ssl.SSLContext":
    """Cria SSLContext mTLS a partir do .pfx, com PEM temporário em disco efêmero."""
    import ssl
    import tempfile
    from pathlib import Path

    cert_pem, key_pem = load_pem_pair(content, password)
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    with tempfile.TemporaryDirectory() as tmp:
        cert_file = Path(tmp) / "cert.pem"
        key_file = Path(tmp) / "key.pem"
        cert_file.write_bytes(cert_pem)
        key_file.write_bytes(key_pem)
        context.load_cert_chain(certfile=str(cert_file), keyfile=str(key_file))
    return context


import ssl
import tempfile
from pathlib import Path

from stk_os.fiscal.signing import CertificateConfigurationError, CertificateMaterial


def material_for(session, establishment_config) -> CertificateMaterial:
    """Devolve cert/chave em PEM, apenas em memória, para assinar o DPS."""
    certificate_pem, private_key_pem = load_pem_pair(session, establishment_config)
    return CertificateMaterial(certificate_pem, private_key_pem, None)


def ssl_context_for(session, establishment_config) -> ssl.SSLContext:
    """Cria o SSLContext mTLS a partir do A1 descriptografado."""
    certificate_pem, private_key_pem = load_pem_pair(session, establishment_config)
    context = ssl.create_default_context()
    with tempfile.TemporaryDirectory() as tmp:
        chain = Path(tmp) / "client.pem"
        chain.write_bytes(certificate_pem + b"\n" + private_key_pem)
        try:
            context.load_cert_chain(str(chain))
        except ssl.SSLError as error:
            raise CertificateConfigurationError(
                "Certificado A1 inválido ou senha incorreta"
            ) from error
    return context
