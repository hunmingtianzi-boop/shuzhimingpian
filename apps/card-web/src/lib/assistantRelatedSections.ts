import type { AssistantCitation } from "./assistantApi";

export type AssistantRelatedSection = {
  id: string;
  targetId: string;
  title: string;
  description: string;
  keywords: string[];
};

function normalizedMatchText(value: string) {
  return value
    .toLocaleLowerCase("zh-CN")
    .replace(/[\s，。！？、,.!?：:；;（）()【】\[\]“”‘’'"·—_\-/\\]/g, "");
}

const GENERIC_SECTION_TERMS = new Set([
  "ai",
  "企业",
  "业务",
  "服务",
  "项目",
  "案例",
  "合作",
  "平台",
  "能力",
  "数据",
]);

function partialTitleScore(title: string, content: string) {
  const normalizedTitle = normalizedMatchText(title);
  const maxLength = Math.min(8, normalizedTitle.length);
  for (let length = maxLength; length >= 3; length -= 1) {
    for (let start = 0; start + length <= normalizedTitle.length; start += 1) {
      const part = normalizedTitle.slice(start, start + length);
      if (!GENERIC_SECTION_TERMS.has(part) && content.includes(part)) return 40 + length;
    }
  }
  return 0;
}

export function matchAssistantRelatedSections(
  text: string,
  citations: AssistantCitation[] | undefined,
  sections: AssistantRelatedSection[],
  limit = 2,
) {
  const content = normalizedMatchText([
    text,
    ...(citations ?? []).map((citation) => citation.label),
  ].join(" "));
  if (!content) return [];

  return sections
    .map((section, index) => {
      const normalizedTitle = normalizedMatchText(section.title);
      let score = normalizedTitle.length >= 3 && content.includes(normalizedTitle)
        ? 1000 + normalizedTitle.length
        : partialTitleScore(section.title, content);
      for (const keyword of section.keywords) {
        const normalizedKeyword = normalizedMatchText(keyword);
        if (
          normalizedKeyword.length >= 2 &&
          !GENERIC_SECTION_TERMS.has(normalizedKeyword) &&
          content.includes(normalizedKeyword)
        ) {
          score = Math.max(score, 100 + normalizedKeyword.length);
        }
      }
      return { section, score, index };
    })
    .filter((item) => item.score > 0)
    .sort((left, right) => right.score - left.score || left.index - right.index)
    .slice(0, Math.max(0, limit))
    .map((item) => item.section);
}
