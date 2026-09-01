from __future__ import annotations

import base64
import hashlib
import os
import ssl
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.serialization import pkcs12
from sqlalchemy import text

from stk_os.fiscal.signing import CertificateConfigurationError, CertificateMaterial


class CertificateError(ValueError):
    """Certificado inválido ou senha incorreta."""


def _key() -> AESGCM:
    raw = os.environ.get("STK_CERT_ENCRYPTION_KEY")
    if not raw:
        raise CertificateError("STK_CERT_ENCRYPTION_KEY não configurada")
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
        raise CertificateError("Não foi possível abrir o .pfx com a senha informada") from error
    if private_key is None or certificate is None:
        raise CertificateError("O arquivo não contém chave privada e certificado")
    return {
        "subject_name": certificate.subject.rfc4514_string(),
        "not_valid_before": certificate.not_valid_before_utc,
        "not_valid_after": certificate.not_valid_after_utc,
        "thumbprint_sha256": hashlib.sha256(content).hexdigest(),
        "expired": certificate.not_valid_after_utc < datetime.now(UTC),
    }


def load_pem_pair(content: bytes, password: str) -> tuple[bytes, bytes]:
    try:
        private_key, certificate, _chain = pkcs12.load_key_and_certificates(
            content, password.encode()
        )
    except Exception as error:
        raise CertificateConfigurationError("Certificado A1 inválido ou senha incorreta") from error
    if private_key is None or certificate is None:
        raise CertificateConfigurationError("O A1 não contém certificado e chave privada")
    return (
        certificate.public_bytes(serialization.Encoding.PEM),
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
    )


def new_key_id(establishment_id: uuid.UUID, environment: str) -> str:
    return f"est-{establishment_id.hex[:12]}-{environment}"


def ssl_context_from_pfx(content: bytes, password: str) -> ssl.SSLContext:
    certificate_pem, private_key_pem = load_pem_pair(content, password)
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    with tempfile.TemporaryDirectory() as temporary_directory:
        directory = Path(temporary_directory)
        certificate_file = directory / "certificate.pem"
        private_key_file = directory / "private-key.pem"
        certificate_file.write_bytes(certificate_pem)
        private_key_file.write_bytes(private_key_pem)
        context.load_cert_chain(str(certificate_file), str(private_key_file))
    return context


_CERTIFICATE_QUERY = text(
    """
    SELECT material_ciphertext, material_nonce,
           password_ciphertext, password_nonce
      FROM public.fiscal_certificates
     WHERE establishment_id = :establishment_id
       AND certificate_key_id = :certificate_key_id
       AND status = 'active'
       AND (environment = :environment OR environment IS NULL)
       AND material_ciphertext IS NOT NULL
       AND password_ciphertext IS NOT NULL
     ORDER BY created_at DESC
     LIMIT 1
    """
)


def _load_stored_material(session, establishment_config) -> tuple[bytes, str]:
    row = session.execute(
        _CERTIFICATE_QUERY,
        {
            "establishment_id": establishment_config.establishment_id,
            "certificate_key_id": establishment_config.certificate_key_id,
            "environment": establishment_config.environment,
        },
    ).first()
    if row is None:
        raise CertificateConfigurationError(
            "Nenhum certificado A1 ativo para este emissor, ambiente e certificate_key_id"
        )
    pfx = decrypt(bytes(row[0]), bytes(row[1]))
    password = decrypt(bytes(row[2]), bytes(row[3])).decode()
    return pfx, password


def material_for(session, establishment_config) -> CertificateMaterial:
    pfx, password = _load_stored_material(session, establishment_config)
    certificate_pem, private_key_pem = load_pem_pair(pfx, password)
    return CertificateMaterial(certificate_pem, private_key_pem, None)


def ssl_context_for(session, establishment_config) -> ssl.SSLContext:
    pfx, password = _load_stored_material(session, establishment_config)
    return ssl_context_from_pfx(pfx, password)
