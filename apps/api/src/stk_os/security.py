from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError

from stk_os.config import get_settings

password_hash = PasswordHash.recommended()


def hash_secret(secret: str) -> str:
    return password_hash.hash(secret)


def verify_secret(secret: str, encoded: str) -> bool:
    try:
        return password_hash.verify(secret, encoded)
    except UnknownHashError:
        # A legacy, truncated or otherwise unsupported database value is an
        # invalid credential. It must never turn a public login attempt into
        # an internal server error.
        return False


def create_access_token(*, actor_id: uuid.UUID, actor_kind: str, permissions: set[str]) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(actor_id),
        "kind": actor_kind,
        "permissions": sorted(permissions),
        "iss": settings.jwt_issuer,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    return jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=["HS256"],
        issuer=settings.jwt_issuer,
        options={"require": ["sub", "kind", "iss", "iat", "exp", "jti"]},
    )


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
