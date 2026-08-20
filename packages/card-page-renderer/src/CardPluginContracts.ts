export const CARD_PLUGIN_HOST_API_VERSION = "1.0.0" as const;

export type CardPluginTrust = "system" | "builtin";

export type CardPluginPermission =
  | "knowledge.published.read"
  | "public_action.open";

export type CardPluginReference = {
  pluginId: string;
  pluginVersion: string;
  contributionId: string;
  pluginConfig?: Record<string, unknown>;
};

export type CardBlockPluginManifest = {
  schemaVersion: 1;
  id: string;
  version: string;
  hostApi: "1.x";
  trust: CardPluginTrust;
  required: boolean;
  commercialFeatureId: string;
  permissions: readonly CardPluginPermission[];
  contributions: readonly {
    id: string;
    legacyType: string;
    configSchema: string;
  }[];
};

export const CARD_BLOCK_PLUGIN_MANIFESTS = [
  {
    schemaVersion: 1,
    id: "cf.system.identity",
    version: "1.0.0",
    hostApi: "1.x",
    trust: "system",
    required: true,
    commercialFeatureId: "card.core",
    permissions: [],
    contributions: [
      {
        id: "identity",
        legacyType: "identity",
        configSchema: "cf.system.identity/config/1",
      },
    ],
  },
  {
    schemaVersion: 1,
    id: "cf.card.faq",
    version: "1.0.0",
    hostApi: "1.x",
    trust: "builtin",
    required: false,
    commercialFeatureId: "card.blocks.faq",
    permissions: ["knowledge.published.read"],
    contributions: [
      {
        id: "faq",
        legacyType: "faq",
        configSchema: "cf.card.faq/config/1",
      },
    ],
  },
  {
    schemaVersion: 1,
    id: "cf.card.actions",
    version: "1.0.0",
    hostApi: "1.x",
    trust: "builtin",
    required: false,
    commercialFeatureId: "card.blocks.actions",
    permissions: ["public_action.open"],
    contributions: [
      {
        id: "actions",
        legacyType: "action_collection",
        configSchema: "cf.card.actions/config/1",
      },
    ],
  },
] as const satisfies readonly CardBlockPluginManifest[];

export const LEGACY_CARD_BLOCK_PLUGIN = {
  pluginId: "cf.legacy.card-blocks",
  pluginVersion: "1.0.0",
} as const;

const referenceByLegacyType = new Map<string, CardPluginReference>(
  CARD_BLOCK_PLUGIN_MANIFESTS.flatMap((manifest) =>
    manifest.contributions.map((contribution) => [
      contribution.legacyType,
      {
        pluginId: manifest.id,
        pluginVersion: manifest.version,
        contributionId: contribution.id,
      },
    ] as const),
  ),
);

export function cardPluginReferenceForLegacyType(type: string): CardPluginReference {
  return referenceByLegacyType.get(type) ?? {
    ...LEGACY_CARD_BLOCK_PLUGIN,
    contributionId: type,
  };
}

export function normalizeCardPluginReference(
  type: string,
  value?: Partial<CardPluginReference>,
): CardPluginReference {
  const expected = cardPluginReferenceForLegacyType(type);
  if (
    value?.pluginId === expected.pluginId
    && value.pluginVersion === expected.pluginVersion
    && value.contributionId === expected.contributionId
  ) {
    return {
      ...expected,
      pluginConfig: value.pluginConfig,
    };
  }
  return expected;
}

export function cardPluginManifest(pluginId: string, version: string) {
  return CARD_BLOCK_PLUGIN_MANIFESTS.find(
    (manifest) => manifest.id === pluginId && manifest.version === version,
  );
}
