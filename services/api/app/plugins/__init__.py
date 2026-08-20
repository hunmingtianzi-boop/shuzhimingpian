"""Built-in plugin contracts and registries.

Phase one deliberately discovers only code shipped with the platform release.
Tenant configuration may enable a release, but it can never point at executable
code or a remote package.
"""

from .card_blocks import (
    BUILTIN_CARD_BLOCK_PLUGINS,
    CardBlockPluginRelease,
    PluginReference,
    card_block_plugin_catalog,
    card_block_plugin_reference,
    normalize_block_plugin_config,
    validate_block_plugin_reference,
)

__all__ = [
    "BUILTIN_CARD_BLOCK_PLUGINS",
    "CardBlockPluginRelease",
    "PluginReference",
    "card_block_plugin_catalog",
    "card_block_plugin_reference",
    "normalize_block_plugin_config",
    "validate_block_plugin_reference",
]
