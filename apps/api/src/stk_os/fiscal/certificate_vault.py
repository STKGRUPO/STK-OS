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


def _load_stored_material(session, establishment_config) -> tuple[bytes, str]:
    """Busca o .pfx e a senha cifrados em fiscal_certificates e descriptografa."""
    from sqlalchemy import select
    from stk_os.models import FiscalCertificate  # ajuste se o nome do modelo for outro

    certificate = session.scalar(
        select(FiscalCertificate)
        .where(
            FiscalCertificate.establishment_id == establishment_config.establishment_id,
            FiscalCertificate.environment == establishment_config.environment,
            FiscalCertificate.status == "active",
        )
        .order_by(FiscalCertificate.created_at.desc())
        .limit(1)
    )
    if certificate is None:
        raise CertificateConfigurationError(
            "Nenhum certificado A1 ativo para este emissor e ambiente"
        )
    pfx = decrypt(certificate.material_ciphertext, certificate.material_nonce)
    password = decrypt(certificate.password_ciphertext, certificate.password_nonce).decode()
    return pfx, password


def material_for(session, establishment_config) -> CertificateMaterial:
    """Devolve cert/chave em PEM, apenas em memória, para assinar o DPS."""
    pfx, password = _load_stored_material(session, establishment_config)
    certificate_pem, private_key_pem = load_pem_pair(pfx, password)
    return CertificateMaterial(certificate_pem, private_key_pem, None)


def ssl_context_for(session, establishment_config) -> ssl.SSLContext:
    """Cria o SSLContext mTLS a partir do A1 descriptografado."""
    pfx, password = _load_stored_material(session, establishment_config)
    certificate_pem, private_key_pem = load_pem_pair(pfx, password)
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


import ssl
import tempfile
from pathlib import Path

from sqlalchemy import select
from sqlalchemy import text

from stk_os.fiscal.signing import CertificateConfigurationError, CertificateMaterial

_CERTIFICATE_QUERY = text(
    """
    SELECT material_ciphertext, material_nonce,
           password_ciphertext, password_nonce
      FROM public.fiscal_certificates
     WHERE establishment_id = :establishment_id
       AND status = 'active'
       AND (environment = :environment OR environment IS NULL)
       AND material_ciphertext IS NOT NULL
       AND password_ciphertext IS NOT NULL
     ORDER BY created_at DESC
     LIMIT 1
    """
)


def _load_stored_material(session, establishment_config) -> tuple[bytes, str]:
    """Busca o .pfx e a senha cifrados em fiscal_certificates e descriptografa."""
    from stk_os.models import FiscalCertificate  # ajuste se o nome do modelo for outro

    certificate = session.scalar(
        select(FiscalCertificate)
        .where(
            FiscalCertificate.establishment_id == establishment_config.establishment_id,
            FiscalCertificate.environment == establishment_config.environment,
            FiscalCertificate.status == "active",
        )
        .order_by(FiscalCertificate.created_at.desc())
        .limit(1)
    )
    if certificate is None:
    row = session.execute(
        _CERTIFICATE_QUERY,
        {
            "establishment_id": establishment_config.establishment_id,
            "environment": establishment_config.environment,
        },
    ).first()
    if row is None:
        raise CertificateConfigurationError(
            "Nenhum certificado A1 ativo para este emissor e ambiente"
        )
    pfx = decrypt(certificate.material_ciphertext, certificate.material_nonce)
    password = decrypt(certificate.password_ciphertext, certificate.password_nonce).decode()
    pfx = decrypt(bytes(row[0]), bytes(row[1]))
    password = decrypt(bytes(row[2]), bytes(row[3])).decode()
    return pfx, password


    return context
