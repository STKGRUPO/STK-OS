from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Protocol


class DocumentStore(Protocol):
    def put(self, key: str, content: bytes) -> tuple[str, int]: ...

    def path_for(self, key: str) -> Path: ...


class PrivateFilesystemDocumentStore:
    """Storage privado do servidor; a raiz deve ser volume gerenciado fora do repositório."""

    def __init__(self, root: Path):
        self.root = root.resolve()

    def path_for(self, key: str) -> Path:
        candidate = (self.root / key).resolve()
        if self.root not in candidate.parents:
            raise ValueError("Chave de documento inválida")
        return candidate

    def put(self, key: str, content: bytes) -> tuple[str, int]:
        target = self.path_for(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_bytes(content)
        temporary.replace(target)
        return hashlib.sha256(content).hexdigest(), len(content)
