import type { StudioModule } from "./CardStudioComponents";
import type {
  CardPageBlock,
  CardPageIdentity,
  CardPageResolvedData,
} from "./CardPageExperience";
import {
  cardPluginReferenceForLegacyType,
  type CardPluginReference,
} from "./CardPluginContracts";

export type CardBlockPluginAdapterContext = {
  data: CardPageResolvedData;
  resolveResourceUrl: (url: string) => string;
  limited: <T>(items: T[], limit?: number) => T[];
  resolveFaqItems: (
    block: Pick<CardPageBlock, "faqMode" | "faqDocumentIds">,
    items: NonNullable<CardPageResolvedData["faqItems"]>,
  ) => NonNullable<CardPageResolvedData["faqItems"]>;
};

type CardBlockPluginAdapter = {
  reference: CardPluginReference;
  adapt: (
    block: CardPageBlock,
    base: StudioModule,
    context: CardBlockPluginAdapterContext,
  ) => StudioModule;
};

function positionValue(value?: string) {
  return ({
    top_left: "topLeft",
    top_right: "topRight",
    bottom_left: "bottomLeft",
    bottom_right: "bottomRight",
  } as Record<string, string>)[String(value || "")] || value;
}

const adapters: readonly CardBlockPluginAdapter[] = [
  {
    reference: cardPluginReferenceForLegacyType("identity"),
    adapt(block, base, { data, resolveResourceUrl }) {
      const identity: CardPageIdentity | undefined = data.identity;
      base.identity = identity ? {
        ...identity,
        imageUrl: identity.imageUrl ? resolveResourceUrl(identity.imageUrl) : undefined,
        layout: block.presentation?.identityLayout
          || (block.layoutVariant === "vertical" ? "vertical" : "horizontal"),
        background: {
          imageUrl: block.presentation?.background?.assetUrl
            ? resolveResourceUrl(block.presentation.background.assetUrl)
            : undefined,
          fit: block.presentation?.background?.fit,
          position: positionValue(block.presentation?.background?.position),
          aspectRatio: block.presentation?.background?.aspectRatio,
          focalX: block.presentation?.background?.focalX,
          focalY: block.presentation?.background?.focalY,
          scale: block.presentation?.background?.scale,
          opacity: block.presentation?.background?.opacity,
          overlay: block.presentation?.background?.overlay,
        },
      } : undefined;
      return base;
    },
  },
  {
    reference: cardPluginReferenceForLegacyType("faq"),
    adapt(block, base, { data, limited, resolveFaqItems }) {
      base.items = limited(
        resolveFaqItems(block, data.faqItems || []),
        block.itemLimit,
      ).map((item) => ({ ...item }));
      return base;
    },
  },
  {
    reference: cardPluginReferenceForLegacyType("action_collection"),
    adapt(block, base, { limited, resolveResourceUrl }) {
      base.items = limited(block.actionItems || [], block.itemLimit).flatMap((item) => {
        const href = safePluginActionHref(item);
        return href ? [{
          ...item,
          href,
          imageUrl: item.imageUrl ? resolveResourceUrl(item.imageUrl) : undefined,
        }] : [];
      });
      return base;
    },
  },
];

const adapterByKey = new Map(
  adapters.map((adapter) => [
    `${adapter.reference.pluginId}@${adapter.reference.pluginVersion}/${adapter.reference.contributionId}`,
    adapter,
  ]),
);

export function registeredCardBlockPluginKeys() {
  return [...adapterByKey.keys()];
}

export function adaptRegisteredCardPluginBlock(
  block: CardPageBlock,
  base: StudioModule,
  context: CardBlockPluginAdapterContext,
) {
  const reference = {
    ...cardPluginReferenceForLegacyType(block.type),
    ...(block.pluginId ? { pluginId: block.pluginId } : {}),
    ...(block.pluginVersion ? { pluginVersion: block.pluginVersion } : {}),
    ...(block.contributionId ? { contributionId: block.contributionId } : {}),
  };
  return adapterByKey.get(
    `${reference.pluginId}@${reference.pluginVersion}/${reference.contributionId}`,
  )?.adapt(block, base, context);
}

function safePluginActionHref(item: NonNullable<CardPageBlock["actionItems"]>[number]) {
  const value = item.targetValue.trim();
  if (!value || /[\\\u0000-\u001f]/.test(value)) return undefined;
  if (item.targetType === "external_url" || item.targetType === "map") {
    try {
      const url = new URL(value);
      return url.protocol === "https:" ? url.toString() : undefined;
    } catch {
      return undefined;
    }
  }
  if (item.targetType === "internal_path") {
    if (!value.startsWith("/") || value.startsWith("//")) return undefined;
    try {
      const parsed = new URL(value, "https://card.local");
      return parsed.origin === "https://card.local" && !parsed.pathname.split("/").includes("..")
        ? `${parsed.pathname}${parsed.search}${parsed.hash}`
        : undefined;
    } catch {
      return undefined;
    }
  }
  return /^\+?[0-9][0-9() -]{4,24}$/.test(value)
    ? `tel:${value.replace(/[^+\d]/g, "")}`
    : undefined;
}
