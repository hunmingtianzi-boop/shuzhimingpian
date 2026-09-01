from __future__ import annotations

import argparse
import json
import sys
from importlib import import_module
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "services" / "api"
CONTRACT_PATH = ROOT / "packages" / "contracts" / "openapi.json"

sys.path.insert(0, str(API_ROOT))

app = import_module("app.main").app


def _without_runtime_prefix(path: str) -> str:
    prefix = "/api/v1"
    return path.removeprefix(prefix)


def sync_contract(contract: dict[str, Any], implemented: dict[str, Any]) -> dict[str, Any]:
    synced = dict(implemented)
    synced["info"] = contract.get("info", implemented.get("info", {}))
    if "servers" in contract:
        synced["servers"] = contract["servers"]
    synced["paths"] = {
        _without_runtime_prefix(path): operations
        for path, operations in implemented.get("paths", {}).items()
    }
    return synced


def _render(contract: dict[str, Any]) -> str:
    synced = sync_contract(contract, app.openapi())
    return json.dumps(synced, ensure_ascii=False, indent=2) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Synchronize the checked-in OpenAPI contract")
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail without writing when the checked-in contract is stale",
    )
    args = parser.parse_args()
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    current = CONTRACT_PATH.read_text(encoding="utf-8")
    rendered = _render(contract)
    if args.check:
        if current != rendered:
            raise SystemExit("OpenAPI contract is stale; run pnpm contracts:sync")
        print("OpenAPI contract is synchronized")
        return
    CONTRACT_PATH.write_text(rendered, encoding="utf-8")
    print(f"Synchronized {len(app.openapi().get('paths', {}))} OpenAPI paths")


if __name__ == "__main__":
    main()
