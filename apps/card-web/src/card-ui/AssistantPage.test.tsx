import { describe, expect, it } from "vitest";

import type { AssistantCitation } from "../lib/assistantApi";
import {
  matchAssistantRelatedSections,
  type AssistantRelatedSection,
} from "../lib/assistantRelatedSections";

const sections: AssistantRelatedSection[] = [
  {
    id: "overview",
    targetId: "enterprise-overview",
    title: "拓浙 AI 集团企业介绍",
    description: "青年 AI 人才与产业场景共创。",
    keywords: ["拓浙 AI 集团", "企业介绍"],
  },
  {
    id: "solution:scene-service",
    targetId: "enterprise-solution-2",
    title: "AI 场景服务",
    description: "从需求诊断、原型验证到定制开发。",
    keywords: ["AI 场景服务", "需求诊断", "原型验证"],
  },
  {
    id: "case",
    targetId: "enterprise-case",
    title: "首届浙客松 AI 创新实践",
    description: "用真实问题组织跨学科共创。",
    keywords: ["浙客松", "首届浙客松", "代表案例"],
  },
  {
    id: "cooperation",
    targetId: "enterprise-overview",
    title: "合作入口",
    description: "查看合作方向并发起联系。",
    keywords: ["企业合作", "发起合作"],
  },
];

describe("assistant related enterprise sections", () => {
  it("matches the current enterprise solution from the completed answer", () => {
    expect(
      matchAssistantRelatedSections(
        "AI 场景服务从需求诊断与原型验证开始。",
        undefined,
        sections,
      ).map((section) => section.id),
    ).toEqual(["solution:scene-service"]);
  });

  it("uses citation labels, deduplicates matches and returns at most two whitelist entries", () => {
    const citations: AssistantCitation[] = [
      {
        id: "citation-1",
        label: "首届浙客松 AI 创新实践",
        sourceType: "knowledge",
      },
      {
        id: "citation-2",
        label: "浙客松活动资料",
        sourceType: "knowledge",
      },
    ];

    expect(
      matchAssistantRelatedSections(
        "可以先了解 AI 场景服务，再通过企业合作发起对接。",
        citations,
        sections,
      ).map((section) => section.id),
    ).toEqual(["case", "solution:scene-service"]);
  });

  it("does not create arbitrary navigation targets from generic chat or answer text", () => {
    expect(
      matchAssistantRelatedSections(
        "你好，可以继续问我企业业务。javascript:#admin",
        undefined,
        sections,
      ),
    ).toEqual([]);
  });

  it("matches dynamic tenant content instead of relying on tuotu-only titles", () => {
    const dynamicSections: AssistantRelatedSection[] = [
      {
        id: "solution:supply-chain",
        targetId: "enterprise-solution-0",
        title: "供应链优化",
        description: "降低库存波动。",
        keywords: ["供应链优化", "库存波动"],
      },
    ];

    expect(
      matchAssistantRelatedSections(
        "供应链优化可以从库存波动分析开始。",
        undefined,
        dynamicSections,
      ).map((section) => section.targetId),
    ).toEqual(["enterprise-solution-0"]);
  });
});
