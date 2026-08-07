import { ChatCircleDots } from "@phosphor-icons/react";
import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";

import type { AssistantConfig } from "../domain/card";
import type { AssistantRelatedSection } from "../lib/assistantRelatedSections";
import type { AIAssistantHandle } from "./AIAssistant";

type AssistantComponent = typeof import("./AIAssistant").AIAssistant;
type PendingAction = { type: "open" } | { type: "question"; question: string };

let assistantModulePromise: Promise<AssistantComponent> | undefined;

function loadAssistantModule() {
  assistantModulePromise ??= import("./AIAssistant")
    .then((module) => module.AIAssistant)
    .catch((error: unknown) => {
      assistantModulePromise = undefined;
      throw error;
    });
  return assistantModulePromise;
}

export type { AIAssistantHandle };

export const DeferredAIAssistant = forwardRef<
  AIAssistantHandle,
  {
    config: AssistantConfig;
    cardSlug: string;
    onLeadPrompt?: () => void;
    relatedSections?: AssistantRelatedSection[];
    onOpenRelatedSection?: (targetId: string) => void;
    onOpenChange?: (open: boolean) => void;
  }
>(function DeferredAIAssistant(
  { config, cardSlug, onLeadPrompt, relatedSections, onOpenRelatedSection, onOpenChange },
  ref,
) {
  const [Component, setComponent] = useState<AssistantComponent | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [loadFailed, setLoadFailed] = useState(false);
  const innerRef = useRef<AIAssistantHandle>(null);
  const pendingAction = useRef<PendingAction | null>(null);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const prefetch = useCallback(() => {
    void loadAssistantModule().catch(() => undefined);
  }, []);

  const activate = useCallback(async () => {
    if (Component || isLoading) return;
    setIsLoading(true);
    setLoadFailed(false);
    try {
      const loaded = await loadAssistantModule();
      if (mounted.current) setComponent(() => loaded);
    } catch {
      if (mounted.current) setLoadFailed(true);
    } finally {
      if (mounted.current) setIsLoading(false);
    }
  }, [Component, isLoading]);

  const queueAction = useCallback(
    (action: PendingAction) => {
      pendingAction.current = action;
      if (innerRef.current) {
        if (action.type === "open") innerRef.current.open();
        else innerRef.current.openWithQuestion(action.question);
        pendingAction.current = null;
        return;
      }
      void activate();
    },
    [activate],
  );

  useEffect(() => {
    if (!Component || !innerRef.current || !pendingAction.current) return;
    const action = pendingAction.current;
    pendingAction.current = null;
    if (action.type === "open") innerRef.current.open();
    else innerRef.current.openWithQuestion(action.question);
  }, [Component]);

  useImperativeHandle(
    ref,
    () => ({
      open: () => queueAction({ type: "open" }),
      openWithQuestion: (question: string) =>
        queueAction({ type: "question", question }),
    }),
    [queueAction],
  );

  if (Component) {
    return (
      <Component
        ref={innerRef}
        config={config}
        cardSlug={cardSlug}
        onLeadPrompt={onLeadPrompt}
        relatedSections={relatedSections}
        onOpenRelatedSection={onOpenRelatedSection}
        onOpenChange={onOpenChange}
      />
    );
  }

  return (
    <button
      className="assistant-launcher"
      type="button"
      onClick={() => queueAction({ type: "open" })}
      onPointerEnter={prefetch}
      onFocus={prefetch}
      aria-busy={isLoading || undefined}
      aria-label={
        loadFailed ? `${config.launcherAriaLabel}，加载失败，点击重试` : config.launcherAriaLabel
      }
    >
      <span className="assistant-launcher-icon">
        <ChatCircleDots size={22} weight="fill" aria-hidden="true" />
      </span>
      <span className="assistant-launcher-copy">
        <small>{isLoading ? "正在加载" : config.launcherKicker}</small>
        <strong>{loadFailed ? "重试资料助手" : config.launcherLabel}</strong>
      </span>
    </button>
  );
});
