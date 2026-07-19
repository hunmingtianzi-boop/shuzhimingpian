from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
from dataclasses import asdict
from typing import Any

from app.services.knowledge_import import (
    ImportDraft,
    KnowledgeImportError,
    decode_draft,
    parse_payload,
)

_RESULT_PREFIX = b"CF_KNOWLEDGE_IMPORT_RESULT="


def parse_import_payload(
    source_type: str,
    file_name: str,
    payload: bytes,
    *,
    timeout_seconds: int,
) -> list[ImportDraft]:
    """Parse one import in a disposable process with a hard wall-clock limit."""

    command = [
        sys.executable,
        "-m",
        "cf_worker.import_parser",
        "--source-type",
        source_type,
        "--file-name",
        file_name,
    ]
    environment = os.environ.copy()
    # Preserve the parent import path for source-tree test runs. Container
    # deployments use installed wheels, but both execution modes should run
    # the exact same parser child.
    environment["PYTHONPATH"] = os.pathsep.join(value for value in sys.path if value)
    process = subprocess.Popen(  # noqa: S603
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
        env=environment,
    )
    try:
        stdout, _stderr = process.communicate(input=payload, timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        # OCR runtimes may start native helper processes. Kill the entire process
        # group so a timed-out document cannot keep consuming worker resources.
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
        raise KnowledgeImportError("IMPORT_PARSE_TIMEOUT") from exc

    if process.returncode != 0:
        raise KnowledgeImportError("IMPORT_PARSE_PROCESS_FAILED")
    result = _decode_child_result(stdout)
    error = result.get("error")
    if isinstance(error, str) and error:
        raise KnowledgeImportError(error)
    drafts = result.get("drafts")
    if not isinstance(drafts, list):
        raise KnowledgeImportError("IMPORT_PARSE_PROCESS_FAILED")
    try:
        return [
            decode_draft(
                json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            )
            for value in drafts
        ]
    except (TypeError, ValueError) as exc:
        raise KnowledgeImportError("IMPORT_PARSE_PROCESS_FAILED") from exc


def _decode_child_result(stdout: bytes) -> dict[str, Any]:
    if _RESULT_PREFIX not in stdout:
        raise KnowledgeImportError("IMPORT_PARSE_PROCESS_FAILED")
    encoded = stdout.rsplit(_RESULT_PREFIX, 1)[1].strip()
    try:
        value = json.loads(encoded.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise KnowledgeImportError("IMPORT_PARSE_PROCESS_FAILED") from exc
    if not isinstance(value, dict):
        raise KnowledgeImportError("IMPORT_PARSE_PROCESS_FAILED")
    return value


def _emit_result(value: dict[str, Any]) -> None:
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    sys.stdout.buffer.write(_RESULT_PREFIX + encoded + b"\n")
    sys.stdout.buffer.flush()


def _child_main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-type", required=True)
    parser.add_argument("--file-name", required=True)
    args = parser.parse_args()
    payload = sys.stdin.buffer.read()
    try:
        drafts = parse_payload(args.source_type, args.file_name, payload)
    except KnowledgeImportError as exc:
        _emit_result({"error": exc.code})
        return 0
    _emit_result({"drafts": [asdict(draft) for draft in drafts]})
    return 0


if __name__ == "__main__":
    raise SystemExit(_child_main())


__all__ = ["parse_import_payload"]
