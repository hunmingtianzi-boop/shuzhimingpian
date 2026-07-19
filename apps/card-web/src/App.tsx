import { useRef, useState } from "react";

import "./styles.css";

import {
  DeferredPublicExperience,
  type PublicExperienceHandle,
} from "./components/DeferredPublicExperience";
import {
  BusinessCardExperience,
  type BusinessCardExperienceHandle,
} from "./card-ui/BusinessCardExperience";
import type { EnterpriseCardConfig } from "./domain/card";
import { copyText } from "./lib/clipboard";
import { createMockPublicCard, resolveMockCardKind } from "./lib/mockPublicCard";
import type { PublicCardData } from "./lib/publicCardApi";
import { canonicalShareUrl } from "./lib/publicExperienceApi";

export default function App({
  tenant,
  publishedCard,
}: {
  tenant: EnterpriseCardConfig;
  publishedCard?: PublicCardData;
}) {
  const cardExperienceRef = useRef<BusinessCardExperienceHandle>(null);
  const publicExperienceRef = useRef<PublicExperienceHandle>(null);
  const [shareNotice, setShareNotice] = useState<string | null>(null);
  const mockEnabled =
    import.meta.env.DEV || import.meta.env.VITE_ENABLE_CARD_MOCK === "true";
  const mockCardKind = mockEnabled
    ? resolveMockCardKind(window.location.search)
    : undefined;
  const mockCard = mockCardKind ? createMockPublicCard(tenant, mockCardKind) : undefined;
  const renderedCard = mockCard ?? publishedCard;
  const isUnconfiguredTemplate = tenant.isBlankTemplate && !renderedCard;
  const assistantEnabled =
    !mockCard && !isUnconfiguredTemplate && (publishedCard?.ai_assistant.available ?? true);

  const openAssistant = (question?: string) => {
    cardExperienceRef.current?.openAssistant(question?.trim());
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
      <BusinessCardExperience
        ref={cardExperienceRef}
        tenant={tenant}
        card={renderedCard}
        assistantEnabled={assistantEnabled}
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
    </>
  );
}
