from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from app.services.knowledge_import import (
    _OCR_RESULT_PREFIX,
    KnowledgeImportError,
    _ocr_image,
    _pdf_ocr_render_scale,
)


def _emit_result(value: dict[str, Any]) -> None:
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    sys.stdout.buffer.write(_OCR_RESULT_PREFIX + encoded)
    sys.stdout.buffer.flush()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf-path", required=True)
    parser.add_argument("--page-number", type=int, required=True)
    args = parser.parse_args()
    try:
        import fitz

        with fitz.open(args.pdf_path) as document:
            if args.page_number < 0 or args.page_number >= document.page_count:
                raise KnowledgeImportError("IMPORT_PDF_INVALID")
            page = document.load_page(args.page_number)
            scale = _pdf_ocr_render_scale(page.rect.width, page.rect.height)
            pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            text = _ocr_image(pixmap.tobytes("png"))
    except KnowledgeImportError as exc:
        _emit_result({"error": exc.code})
        return 0
    except Exception:
        _emit_result({"error": "IMPORT_PDF_OCR_FAILED"})
        return 0
    _emit_result({"text": text})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
