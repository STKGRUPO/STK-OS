from __future__ import annotations

import json
from pathlib import Path

from stk_os.main import app

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "contracts" / "api" / "openapi.json"


def main() -> None:
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    with TARGET.open("w", encoding="utf-8", newline="\n") as contract_file:
        contract_file.write(
            json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n"
        )
    print(TARGET)


if __name__ == "__main__":
    main()
