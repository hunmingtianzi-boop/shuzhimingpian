from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal, Mapping

PLUGIN_HOST_API_VERSION = "1.0.0"
PLUGIN_VERSION = "1.0.0"

_PLUGIN_ID = re.compile(r"^[a-z][a-z0-9]*(?:\.[a-z][a-z0-9_-]*)+$")
_SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


@dataclass(frozen=True, slots=True)
class PluginReference:
    plugin_id: str
    plugin_version: str
    contribution_id: str

    @property
    def key(self) -> str:
        return f"{self.plugin_id}@{self.plugin_version}/{self.contribution_id}"


@dataclass(frozen=True, slots=True)
class CardBlockPluginRelease:
    plugin_id: str
    version: str
    host_api: str
    trust: Literal["system", "builtin"]
    required: bool
    commercial_feature_id: str
    permissions: tuple[str, ...]
    contribution_id: str
    legacy_type: str
    config_schema: str

    @property
    def reference(self) -> PluginReference:
        return PluginReference(
            plugin_id=self.plugin_id,
            plugin_version=self.version,
            contribution_id=self.contribution_id,
        )


BUILTIN_CARD_BLOCK_PLUGINS = (
    CardBlockPluginRelease(
        plugin_id="cf.system.identity",
        version=PLUGIN_VERSION,
        host_api="1.x",
        trust="system",
        required=True,
        commercial_feature_id="card.core",
        permissions=(),
        contribution_id="identity",
        legacy_type="identity",
        config_schema="cf.system.identity/config/1",
    ),
    CardBlockPluginRelease(
        plugin_id="cf.card.faq",
        version=PLUGIN_VERSION,
        host_api="1.x",
        trust="builtin",
        required=False,
        commercial_feature_id="card.blocks.faq",
        permissions=("knowledge.published.read",),
        contribution_id="faq",
        legacy_type="faq",
        config_schema="cf.card.faq/config/1",
    ),
    CardBlockPluginRelease(
        plugin_id="cf.card.actions",
        version=PLUGIN_VERSION,
        host_api="1.x",
        trust="builtin",
        required=False,
        commercial_feature_id="card.blocks.actions",
        permissions=("public_action.open",),
        contribution_id="actions",
        legacy_type="action_collection",
        config_schema="cf.card.actions/config/1",
    ),
)

LEGACY_PLUGIN_ID = "cf.legacy.card-blocks"

_BY_LEGACY_TYPE = {release.legacy_type: release for release in BUILTIN_CARD_BLOCK_PLUGINS}
_BY_KEY = {release.reference.key: release for release in BUILTIN_CARD_BLOCK_PLUGINS}


def _validate_registry() -> None:
    keys: set[str] = set()
    legacy_types: set[str] = set()
    for release in BUILTIN_CARD_BLOCK_PLUGINS:
        if not _PLUGIN_ID.fullmatch(release.plugin_id):
            raise RuntimeError(f"invalid built-in plugin id: {release.plugin_id}")
        if not _SEMVER.fullmatch(release.version):
            raise RuntimeError(f"invalid built-in plugin version: {release.version}")
        if release.host_api != "1.x":
            raise RuntimeError(f"unsupported built-in plugin host API: {release.host_api}")
        if release.reference.key in keys:
            raise RuntimeError(f"duplicate built-in plugin contribution: {release.reference.key}")
        if release.legacy_type in legacy_types:
            raise RuntimeError(f"duplicate legacy block mapping: {release.legacy_type}")
        keys.add(release.reference.key)
        legacy_types.add(release.legacy_type)


_validate_registry()


def card_block_plugin_reference(block_type: str) -> PluginReference:
    release = _BY_LEGACY_TYPE.get(block_type)
    if release is not None:
        return release.reference
    return PluginReference(
        plugin_id=LEGACY_PLUGIN_ID,
        plugin_version=PLUGIN_VERSION,
        contribution_id=block_type,
    )


def validate_block_plugin_reference(
    *,
    block_type: str,
    plugin_id: str | None,
    plugin_version: str | None,
    contribution_id: str | None,
) -> PluginReference:
    expected = card_block_plugin_reference(block_type)
    values = (plugin_id, plugin_version, contribution_id)
    if all(value is None for value in values):
        return expected
    if any(value is None for value in values):
        raise ValueError("plugin reference fields must be provided together")
    provided = PluginReference(
        plugin_id=str(plugin_id),
        plugin_version=str(plugin_version),
        contribution_id=str(contribution_id),
    )
    if provided != expected:
        raise ValueError(
            f"block type {block_type!r} requires plugin contribution {expected.key}"
        )
    return provided


def expand_block_plugin_config(value: Mapping[str, Any]) -> dict[str, Any]:
    """Project v2 plugin config into existing validated block fields.

    Keeping this adapter at the schema boundary lets legacy and v2 documents use
    the same mature resource validation while the remaining block types migrate.
    """

    result = dict(value)
    block_type = result.get("type")
    config = result.get("config")
    if config is None:
        return result
    if not isinstance(config, Mapping):
        raise ValueError("plugin config must be an object")
    allowed_by_type = {
        "identity": {"presentation"},
        "faq": {"mode", "document_ids"},
        "action_collection": {"template", "items"},
    }
    allowed = allowed_by_type.get(str(block_type), set())
    unknown = set(config) - allowed
    if unknown:
        raise ValueError(f"unsupported plugin config fields: {sorted(unknown)}")
    if block_type == "identity" and "presentation" in config:
        result["presentation"] = config["presentation"]
    elif block_type == "faq":
        if "mode" in config:
            result["faq_mode"] = config["mode"]
        if "document_ids" in config:
            result["faq_document_ids"] = config["document_ids"]
    elif block_type == "action_collection":
        if "template" in config:
            result["action_template"] = config["template"]
        if "items" in config:
            result["action_items"] = config["items"]
    elif config:
        raise ValueError("legacy card blocks do not accept plugin config")
    return result


def normalize_block_plugin_config(block_type: str, values: Mapping[str, Any]) -> dict[str, Any]:
    if block_type == "identity":
        presentation = values.get("presentation")
        return {"presentation": presentation} if presentation is not None else {}
    if block_type == "faq":
        mode = values.get("faq_mode") or "all_published"
        document_ids = values.get("faq_document_ids") or []
        return {
            "mode": mode,
            "document_ids": document_ids if mode == "selected" else [],
        }
    if block_type == "action_collection":
        return {
            "template": values.get("action_template") or "shortcuts",
            "items": values.get("action_items") or [],
        }
    return {}


def card_block_plugin_catalog(*, killed: set[str] | None = None) -> list[dict[str, Any]]:
    killed = killed or set()
    return [
        {
            "schema_version": 1,
            "id": release.plugin_id,
            "version": release.version,
            "host_api": release.host_api,
            "trust": release.trust,
            "required": release.required,
            "commercial_feature_id": release.commercial_feature_id,
            "permissions": list(release.permissions),
            "status": "killed" if release.reference.key in killed else "available",
            "contributions": [
                {
                    "id": release.contribution_id,
                    "legacy_type": release.legacy_type,
                    "config_schema": release.config_schema,
                }
            ],
        }
        for release in BUILTIN_CARD_BLOCK_PLUGINS
    ]


def plugin_release_for_reference(reference: PluginReference) -> CardBlockPluginRelease | None:
    return _BY_KEY.get(reference.key)
