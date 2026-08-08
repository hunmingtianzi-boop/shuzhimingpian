from __future__ import annotations

from typing import Any


def default_enterprise_template() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "theme_key": "brand",
        "blocks": [
            {
                "id": "identity",
                "type": "identity",
                "visible": True,
                "directory_enabled": False,
                "sort_order": 0,
                "title": "基础名片",
            },
            {
                "id": "overview",
                "type": "rich_text",
                "visible": True,
                "sort_order": 1,
                "title": "概览",
            },
            {
                "id": "intro",
                "type": "rich_text",
                "visible": True,
                "sort_order": 2,
                "title": "企业介绍",
            },
            {
                "id": "business",
                "type": "business_collection",
                "visible": True,
                "sort_order": 3,
                "title": "核心业务",
            },
            {
                "id": "cases",
                "type": "case_collection",
                "visible": True,
                "sort_order": 4,
                "title": "代表案例",
            },
            {
                "id": "trust",
                "type": "trust_panel",
                "visible": True,
                "sort_order": 5,
                "title": "企业资料",
            },
            {"id": "faq", "type": "faq", "visible": True, "sort_order": 6, "title": "常见问题"},
            {
                "id": "ai",
                "type": "ai_assistant",
                "visible": True,
                "sort_order": 7,
                "title": "企业 AI 助手",
            },
        ],
    }


def merge_default_template_blocks(blocks: list[object]) -> list[dict[str, Any]]:
    indexed = [(index, block) for index, block in enumerate(blocks) if isinstance(block, dict)]
    merged = [
        block
        for _, block in sorted(
            indexed,
            key=lambda item: (
                item[1].get("sort_order")
                if isinstance(item[1].get("sort_order"), int)
                else item[0],
                item[0],
            ),
        )
    ]
    defaults = default_enterprise_template()["blocks"]
    matched_default_ids: set[str] = set()

    def matches_default(block: dict[str, Any], default_block: dict[str, Any]) -> bool:
        return bool(
            block.get("id") == default_block["id"]
            or (default_block["type"] != "rich_text" and block.get("type") == default_block["type"])
            or (
                default_block["type"] == "rich_text"
                and block.get("type") == "rich_text"
                and block.get("title") == default_block.get("title")
            )
        )

    for index, block in enumerate(merged):
        match = next(
            (
                default_block
                for default_block in defaults
                if default_block["id"] not in matched_default_ids
                and matches_default(block, default_block)
            ),
            None,
        )
        if match is None:
            continue
        matched_default_ids.add(str(match["id"]))
        if match["type"] == "identity":
            merged[index] = {
                **block,
                "visible": True,
                "directory_enabled": block.get("directory_enabled", match["directory_enabled"]),
            }

    for default_block in defaults:
        if default_block["id"] in matched_default_ids:
            continue
        insert_at = min(int(default_block["sort_order"]), len(merged))
        merged.insert(insert_at, default_block)
    return [{**block, "sort_order": index} for index, block in enumerate(merged)]
