import type { ReactNode } from "react";

export type CardPageBlockSelector<T> = {
  getId: (block: T) => string;
  getSortOrder: (block: T) => number;
  isVisible: (block: T) => boolean;
};

export function orderVisibleCardPageBlocks<T>(
  blocks: T[],
  selector: CardPageBlockSelector<T>,
) {
  return blocks
    .filter(selector.isVisible)
    .sort((left, right) => selector.getSortOrder(left) - selector.getSortOrder(right));
}

export function deriveCardPageDirectory<T>(
  blocks: T[],
  selector: CardPageBlockSelector<T> & {
    getTitle: (block: T) => string | undefined;
    isDirectoryEnabled: (block: T) => boolean;
  },
) {
  return orderVisibleCardPageBlocks(blocks, selector).flatMap((block) => {
    const title = selector.getTitle(block)?.trim();
    return title && selector.isDirectoryEnabled(block)
      ? [{ id: selector.getId(block), title }]
      : [];
  });
}

export function CardPageBlocksRenderer<T>({
  blocks,
  selector,
  className,
  ariaLabel,
  blockElement = "article",
  blockClassName,
  getBlockDataType,
  renderBlock,
}: {
  blocks: T[];
  selector: CardPageBlockSelector<T>;
  className: string;
  ariaLabel: string;
  blockElement?: "article" | "section" | "div";
  blockClassName?: (block: T) => string;
  getBlockDataType?: (block: T) => string;
  renderBlock: (block: T) => ReactNode;
}) {
  const visibleBlocks = orderVisibleCardPageBlocks(blocks, selector);
  if (!visibleBlocks.length) return null;
  const BlockElement = blockElement;
  return (
    <section className={className} aria-label={ariaLabel}>
      {visibleBlocks.map((block) => {
        const id = selector.getId(block);
        return (
          <BlockElement
            className={blockClassName?.(block)}
            key={id}
            id={`bp-template-block-${id}`}
            tabIndex={-1}
            data-card-page-block={id}
            data-template-block={getBlockDataType?.(block)}
          >
            {renderBlock(block)}
          </BlockElement>
        );
      })}
    </section>
  );
}
