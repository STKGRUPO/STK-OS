from __future__ import annotations

import base64
import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from lxml import etree

DS = "http://www.w3.org/2000/09/xmldsig#"
NFSE = "http://www.sped.fazenda.gov.br/nfse"
logger = logging.getLogger(__name__)


class CertificateConfigurationError(RuntimeError):
    pass

def c14n(element) -> bytes:
    """Canonicaliza C14N 1.0 sem o artefato xmlns="" que o lxml injeta em subarvores.

    Serializar e reparsear o elemento fixa as declaracoes de namespace no proprio
    elemento, produzindo os mesmos bytes que .NET/Java/SEFIN produzem.
    """
    isolated = etree.fromstring(etree.tostring(element))
    return etree.tostring(isolated, method="c14n", with_comments=False)

@dataclass(frozen=True)
class CertificateMaterial:
    certificate_pem: bytes
    private_key_pem: bytes
    private_key_password: bytes | None = None


class XmlSigner:
    def sign(self, xml: bytes, material: CertificateMaterial) -> bytes:
        try:
            certificate = x509.load_pem_x509_certificate(material.certificate_pem)
            private_key = serialization.load_pem_private_key(
                material.private_key_pem, password=material.private_key_password
            )
        except (TypeError, ValueError) as error:
            raise CertificateConfigurationError("Certificado A1 configurado é inválido") from error
        if not isinstance(private_key, rsa.RSAPrivateKey):
            raise CertificateConfigurationError("O certificado fiscal exige chave privada RSA")
        root = etree.fromstring(xml)
        inf = root.find(f"{{{NFSE}}}infDPS")
        if inf is None or not inf.get("Id"):
            raise CertificateConfigurationError("DPS sem infDPS/Id para assinatura")
            
        issuer_node = inf.find(f"{{{NFSE}}}prest/{{{NFSE}}}CNPJ")
        issuer_cnpj = re.sub(r"\D", "", (issuer_node.text or "")) if issuer_node is not None else ""
        subject_cnpjs = re.findall(r"\d{14}", certificate.subject.rfc4514_string())
        if issuer_cnpj and subject_cnpjs and issuer_cnpj not in subject_cnpjs:
            raise CertificateConfigurationError(
                "O certificado A1 cadastrado nao pertence ao CNPJ emissor "
                f"({issuer_cnpj}). Cadastre o e-CNPJ da propria empresa."
            )
        # SHA-1 é exigido pelo comportamento XMLDSIG homologado do legado/SEFIN.
        digest = base64.b64encode(
            hashlib.sha1(c14n(inf), usedforsecurity=False).digest()
        ).decode()
        signature = etree.Element(f"{{{DS}}}Signature", nsmap={None: DS})
        signed_info = etree.SubElement(signature, f"{{{DS}}}SignedInfo")
        etree.SubElement(
            signed_info,
            f"{{{DS}}}CanonicalizationMethod",
            Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315",
        )
        etree.SubElement(
            signed_info,
            f"{{{DS}}}SignatureMethod",
            Algorithm="http://www.w3.org/2000/09/xmldsig#rsa-sha1",
        )
        reference = etree.SubElement(signed_info, f"{{{DS}}}Reference", URI=f"#{inf.get('Id')}")
        transforms = etree.SubElement(reference, f"{{{DS}}}Transforms")
        etree.SubElement(
            transforms,
            f"{{{DS}}}Transform",
            Algorithm="http://www.w3.org/2000/09/xmldsig#enveloped-signature",
        )
        etree.SubElement(
            transforms,
            f"{{{DS}}}Transform",
            Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315",
        )
        etree.SubElement(
            reference,
            f"{{{DS}}}DigestMethod",
            Algorithm="http://www.w3.org/2000/09/xmldsig#sha1",
        )
        etree.SubElement(reference, f"{{{DS}}}DigestValue").text = digest
        # Canonicaliza SignedInfo sem o artefato xmlns="" do lxml (causa do E0714).
        root.append(signature)
        signed = c14n(signed_info)
        value = private_key.sign(signed, padding.PKCS1v15(), hashes.SHA1())  # noqa: S303
        etree.SubElement(signature, f"{{{DS}}}SignatureValue").text = base64.b64encode(
            value
        ).decode()
        key_info = etree.SubElement(signature, f"{{{DS}}}KeyInfo")
        x509_data = etree.SubElement(key_info, f"{{{DS}}}X509Data")
        etree.SubElement(x509_data, f"{{{DS}}}X509Certificate").text = base64.b64encode(
            certificate.public_bytes(serialization.Encoding.DER)
        ).decode()
        payload = etree.tostring(root, xml_declaration=True, encoding="UTF-8")

        # Autoverificacao: refaz digest e assinatura a partir do XML final.
        check_root = etree.fromstring(payload)
        check_inf = check_root.find(f"{{{NFSE}}}infDPS")
        check_sig = check_root.find(f"{{{DS}}}Signature")
        if check_inf is None or check_sig is None:
            raise CertificateConfigurationError(
                "XML final sem infDPS ou Signature para autoverificacao"
            )

        check_signed_info = check_sig.find(f"{{{DS}}}SignedInfo")
        check_signature_value = check_sig.findtext(f"{{{DS}}}SignatureValue")
        stored_digest = check_sig.findtext(
            f"{{{DS}}}SignedInfo/{{{DS}}}Reference/{{{DS}}}DigestValue"
        )
        if check_signed_info is None or not check_signature_value or not stored_digest:
            raise CertificateConfigurationError(
                "XML final com estrutura XMLDSIG incompleta"
            )

        recomputed_digest = base64.b64encode(
            hashlib.sha1(  # noqa: S324
                c14n(check_inf),
                usedforsecurity=False,
            ).digest()
        ).decode()
        digest_ok = recomputed_digest == stored_digest

        try:
            certificate.public_key().verify(  # type: ignore[union-attr]
                base64.b64decode(check_signature_value),
                c14n(check_signed_info),
                padding.PKCS1v15(),
                hashes.SHA1(),  # noqa: S303
            )
            signature_ok = True
        except Exception:  # noqa: BLE001
            signature_ok = False

        # Os resultados ficam no texto porque o formatador atual nao mostra extra={...}.
        logger.info(
            "dps_signed dps_id=%s digest_ok=%s signature_ok=%s "
            "digest_value=%s signed_sha256=%s signed_bytes=%s",
            inf.get("Id"),
            digest_ok,
            signature_ok,
            digest,
            hashlib.sha256(payload).hexdigest(),
            len(payload),
        )

        return payload


class MountedSecretResolver:
    """Resolve material provisionado por vault/secret store em volume somente leitura."""

    def __init__(self, root: Path):
        self.root = root.resolve()

    def resolve(self, key_id: str) -> CertificateMaterial:
        safe_key_id = key_id.replace("-", "_")
        if not safe_key_id or any(
            char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"
            for char in safe_key_id
        ):
            raise CertificateConfigurationError("Identificador do certificado é inválido")
        directory = (self.root / safe_key_id).resolve()
        if self.root not in directory.parents:
            raise CertificateConfigurationError(
                "Referência do certificado está fora do secret mount"
            )
        try:
            certificate = (directory / "certificate.pem").read_bytes()
            private_key = (directory / "private-key.pem").read_bytes()
            password_path = directory / "password"
            password = password_path.read_bytes().strip() if password_path.exists() else None
        except OSError as error:
            raise CertificateConfigurationError(
                "Certificado A1 não foi provisionado no secret mount do serviço"
            ) from error
        return CertificateMaterial(certificate, private_key, password or None)
