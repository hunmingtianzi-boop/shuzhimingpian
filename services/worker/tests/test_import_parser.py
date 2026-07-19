from __future__ import annotations

import subprocess

import pytest
from app.services.knowledge_import import KnowledgeImportError

from cf_worker import import_parser


def test_parser_process_round_trips_draft() -> None:
    drafts = import_parser.parse_import_payload(
        "txt",
        "企业介绍.txt",
        "析境科技提供专业服务。".encode(),
        timeout_seconds=30,
    )

    assert len(drafts) == 1
    assert drafts[0].title == "企业介绍"
    assert drafts[0].raw_text == "析境科技提供专业服务。"


def test_parser_process_preserves_domain_error() -> None:
    with pytest.raises(KnowledgeImportError, match="IMPORT_PDF_INVALID"):
        import_parser.parse_import_payload(
            "pdf", "broken.pdf", b"%PDF-broken", timeout_seconds=30
        )


def test_parser_process_enforces_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    class HungProcess:
        pid = 123

        def communicate(self, *, input=None, timeout=None):
            if timeout is not None:
                raise subprocess.TimeoutExpired("parser", timeout)
            return b"", b""

    monkeypatch.setattr(import_parser.subprocess, "Popen", lambda *args, **kwargs: HungProcess())
    monkeypatch.setattr(import_parser.os, "killpg", lambda *args: None)

    with pytest.raises(KnowledgeImportError, match="IMPORT_PARSE_TIMEOUT"):
        import_parser.parse_import_payload("txt", "file.txt", b"text", timeout_seconds=30)


def test_parser_process_rejects_missing_result_marker(monkeypatch: pytest.MonkeyPatch) -> None:
    class BrokenProcess:
        pid = 123
        returncode = 0

        def communicate(self, *, input=None, timeout=None):
            return b"unexpected output", b""

    monkeypatch.setattr(import_parser.subprocess, "Popen", lambda *args, **kwargs: BrokenProcess())

    with pytest.raises(KnowledgeImportError, match="IMPORT_PARSE_PROCESS_FAILED"):
        import_parser.parse_import_payload("txt", "file.txt", b"text", timeout_seconds=30)
