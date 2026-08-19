from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IGNORED_PARTS = {".git", ".venv", "node_modules", ".next", ".npm-cache"}
TEXT_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".json",
    ".yml",
    ".yaml",
    ".md",
    ".sql",
    ".toml",
}
PATTERNS = {
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "JWT": re.compile(
        r"\beyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\b"
    ),
}


def main() -> None:
    findings: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in IGNORED_PARTS for part in path.parts):
            continue
        if path.name == ".env.example":
            if any(
                line.partition("=")[2].strip() for line in path.read_text().splitlines()
            ):
                findings.append(f"{path.relative_to(ROOT)}: .env.example contém valor")
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        content = path.read_text(encoding="utf-8", errors="ignore")
        for label, pattern in PATTERNS.items():
            if pattern.search(content):
                findings.append(f"{path.relative_to(ROOT)}: possível {label}")
    if findings:
        raise SystemExit("\n".join(findings))
    print("secret scan: ok")


if __name__ == "__main__":
    main()
