import { useMemo, useRef, useState } from "react";

import "./styles.css";

import {
  DeferredAIAssistant,
  type AIAssistantHandle,
} from "./components/DeferredAIAssistant";
import {
  DeferredPublicExperience,
  type PublicExperienceHandle,
} from "./components/DeferredPublicExperience";
import type { EnterpriseCardConfig } from "./domain/card";
import type { AssistantRelatedSection } from "./lib/assistantRelatedSections";
import { copyText } from "./lib/clipboard";
import { createMockPublicCard, resolveMockCardKind } from "./lib/mockPublicCard";
import type { PublicCardData } from "./lib/publicCardApi";
import { canonicalShareUrl } from "./lib/publicExperienceApi";
import {
  BusinessCardPrototypeApp,
  type BusinessCardPrototypeAppHandle,
} from "./prototype/BusinessCardPrototypeApp";

export default function App({
  tenant,
  publishedCard,
}: {
  tenant: EnterpriseCardConfig;
  publishedCard?: PublicCardData;
}) {
  const assistantRef = useRef<AIAssistantHandle>(null);
  const prototypeRef = useRef<BusinessCardPrototypeAppHandle>(null);
  const publicExperienceRef = useRef<PublicExperienceHandle>(null);
  const [shareNotice, setShareNotice] = useState<string | null>(null);
  const [assistantRelatedSections, setAssistantRelatedSections] = useState<
    AssistantRelatedSection[]
  >([]);
  const mockEnabled =
    import.meta.env.DEV || import.meta.env.VITE_ENABLE_CARD_MOCK === "true";
  const mockCardKind = mockEnabled
    ? resolveMockCardKind(window.location.search)
    : undefined;
  const mockCard = useMemo(
    () => mockCardKind ? createMockPublicCard(tenant, mockCardKind) : undefined,
    [mockCardKind, tenant],
  );
  const renderedCard = mockCard ?? publishedCard;
  const isUnconfiguredTemplate = tenant.isBlankTemplate && !renderedCard;
  const assistantEnabled =
    !mockCard &&
    !isUnconfiguredTemplate &&
    (publishedCard?.ai_assistant.available ?? true);

  const openAssistant = (question?: string) => {
    if (mockCard) {
      setShareNotice(`模拟 AI 接待${question?.trim() ? `：${question.trim()}` : "已打开"}`);
      return;
    }
    if (question?.trim()) assistantRef.current?.openWithQuestion(question.trim());
    else assistantRef.current?.open();
  };

  const openLead = () => {
    if (mockCard) {
      setShareNotice("模拟合作需求表单已打开");
      return;
    }
    if (publishedCard) publicExperienceRef.current?.openLead();
    else openAssistant("我想提交合作需求，请告诉我如何联系");
  };

  const shareFallback = async () => {
    const url = canonicalShareUrl(window.location);
    if (navigator.share) {
      try {
        await navigator.share({ title: tenant.seo.title, text: tenant.seo.description, url });
        return;
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") return;
      }
    }
    try {
      await copyText(url);
      setShareNotice("名片链接已复制");
    } catch {
      setShareNotice(`无法自动复制，请手动复制：${url}`);
    }
  };

  const openShare = () => {
    if (renderedCard) publicExperienceRef.current?.openShare();
    else void shareFallback();
  };

  return (
    <>
      <BusinessCardPrototypeApp
        ref={prototypeRef}
        tenant={tenant}
        card={renderedCard}
        onAssistant={openAssistant}
        onAssistantRelatedSectionsChange={setAssistantRelatedSections}
        onLead={openLead}
        onPrivacy={() => {
          if (mockCard) setShareNotice("模拟隐私与个人信息入口");
          else publicExperienceRef.current?.openPrivacy();
        }}
        onProfile={() => {
          if (mockCard) setShareNotice("模拟访客画像授权入口");
          else publicExperienceRef.current?.openProfile();
        }}
        onShare={openShare}
      />

      {shareNotice && (
        <div className="public-controller-error" role="status">
          <span>{shareNotice}</span>
          <button type="button" onClick={() => setShareNotice(null)}>关闭</button>
        </div>
      )}

      {renderedCard && (
        <DeferredPublicExperience
          ref={publicExperienceRef}
          card={renderedCard}
          controllerOnly
          onAssistant={openAssistant}
        />
      )}

      {assistantEnabled && (
        <DeferredAIAssistant
          key={tenant.id}
          ref={assistantRef}
          config={tenant.assistant}
          cardSlug={publishedCard?.slug ?? tenant.id}
          onLeadPrompt={publishedCard ? openLead : undefined}
          relatedSections={assistantRelatedSections}
          onOpenRelatedSection={(targetId) => {
            prototypeRef.current?.openAssistantTarget(targetId);
          }}
        />
      )}
    </>
  );
}
