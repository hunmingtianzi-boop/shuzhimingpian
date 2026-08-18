import { useCallback, useEffect, useRef } from "react";

import {
  createAssistantIdempotencyKey,
  ensureVisitSession,
  markVisitorSessionBackground,
  recordVisitEvent,
  resumeVisitorSession,
  type PublicPolicyVersions,
  type VisitorSession,
} from "./assistantApi";

export type AnalyticsPage = {
  key: string;
  title: string;
  objectType: "card" | "product" | "case" | "faq" | "contact" | "ai";
  objectId?: string;
};

type ActivePage = AnalyticsPage & { enteredAt: number };

export function useVisitAnalytics({
  enabled,
  cardSlug,
  companyId,
  policyVersions,
}: {
  enabled: boolean;
  cardSlug: string;
  companyId?: string;
  policyVersions?: PublicPolicyVersions;
}) {
  const sessionRef = useRef<VisitorSession | undefined>(undefined);
  const activePageRef = useRef<ActivePage | undefined>(undefined);
  const queueRef = useRef<Promise<void>>(Promise.resolve());
  const entryRef = useRef<
    { cardSlug: string; id: string; acknowledged: boolean } | undefined
  >(undefined);
  if (!entryRef.current || entryRef.current.cardSlug !== cardSlug) {
    entryRef.current = {
      cardSlug,
      id: createAssistantIdempotencyKey(),
      acknowledged: false,
    };
  }

  const enqueue = useCallback((operation: () => Promise<void>) => {
    queueRef.current = queueRef.current
      .catch(() => undefined)
      .then(operation)
      .catch(() => undefined);
  }, []);

  const sendPageView = useCallback((page: ActivePage) => {
    const session = sessionRef.current;
    if (!session) return;
    const entry = entryRef.current;
    const visitEntryId = entry?.cardSlug === cardSlug && !entry.acknowledged
      ? entry.id
      : undefined;
    enqueue(async () => {
      await recordVisitEvent({
        cardSlug,
        session,
        eventType: "page_view",
        objectType: page.objectType,
        objectId: page.objectId,
        metadata: {
          page_key: page.key,
          page_title: page.title,
          ...(visitEntryId ? { visit_entry_id: visitEntryId } : {}),
        },
      });
      if (visitEntryId && entryRef.current?.id === visitEntryId) {
        entryRef.current.acknowledged = true;
      }
    });
  }, [cardSlug, enqueue]);

  const beginSession = useCallback((signal?: AbortSignal) => {
    if (!policyVersions) return Promise.resolve();
    return ensureVisitSession({
      cardSlug,
      companyId,
      policyVersions,
      signal,
    }).then((session) => {
      if (signal?.aborted) return;
      sessionRef.current = session;
      const page = activePageRef.current;
      if (page) sendPageView(page);
    }).catch(() => undefined);
  }, [cardSlug, companyId, policyVersions, sendPageView]);

  const flushDuration = useCallback((
    eventType: "heartbeat" | "leave",
    keepalive = false,
    lifecycleState?: "background",
  ) => {
    const session = sessionRef.current;
    const page = activePageRef.current;
    if (!session || !page) return;
    const durationMs = Math.max(0, Math.round(performance.now() - page.enteredAt));
    page.enteredAt = performance.now();
    const operation = () => recordVisitEvent({
      cardSlug,
      session,
      eventType,
      objectType: page.objectType,
      objectId: page.objectId,
      metadata: {
        page_key: page.key,
        page_title: page.title,
        duration_ms: durationMs,
        ...(lifecycleState ? { lifecycle_state: lifecycleState } : {}),
      },
      keepalive,
    });
    if (keepalive) void operation().catch(() => undefined);
    else enqueue(operation);
  }, [cardSlug, enqueue]);

  const trackPage = useCallback((page: AnalyticsPage) => {
    const current = activePageRef.current;
    if (current?.key === page.key) return;
    if (current) flushDuration("heartbeat");
    const next = { ...page, enteredAt: performance.now() };
    activePageRef.current = next;
    sendPageView(next);
  }, [flushDuration, sendPageView]);

  const trackAction = useCallback((
    eventType: "content_view" | "cta_click" | "share",
    objectType: AnalyticsPage["objectType"],
    objectId: string,
    metadata: Record<string, string | number | boolean | null> = {},
  ) => {
    const session = sessionRef.current;
    if (!session) return;
    enqueue(() => recordVisitEvent({
      cardSlug,
      session,
      eventType,
      objectType,
      objectId,
      metadata,
    }));
  }, [cardSlug, enqueue]);

  useEffect(() => {
    if (!enabled || !policyVersions) return undefined;
    const controller = new AbortController();
    void beginSession(controller.signal);
    return () => controller.abort();
  }, [beginSession, enabled, policyVersions]);

  useEffect(() => {
    if (!enabled) return undefined;
    const intervalId = window.setInterval(() => {
      if (document.visibilityState === "visible") {
        flushDuration("heartbeat");
      }
    }, 10_000);
    return () => window.clearInterval(intervalId);
  }, [enabled, flushDuration]);

  useEffect(() => {
    if (!enabled) return undefined;
    const visibilityChanged = () => {
      if (document.visibilityState === "hidden") {
        // Enterprise WeChat commonly keeps the card WebView alive when the
        // user switches back to the workbench, so pagehide never fires. Mark
        // that transition explicitly while keeping the visit resumable.
        markVisitorSessionBackground(cardSlug);
        flushDuration("heartbeat", true, "background");
      } else {
        const shouldStartNewVisit = resumeVisitorSession(cardSlug);
        const page = activePageRef.current;
        if (page) page.enteredAt = performance.now();
        if (shouldStartNewVisit) {
          sessionRef.current = undefined;
          entryRef.current = {
            cardSlug,
            id: createAssistantIdempotencyKey(),
            acknowledged: false,
          };
          void beginSession();
        } else if (page) {
          sendPageView(page);
        }
      }
    };
    const pageHidden = () => {
      markVisitorSessionBackground(cardSlug);
      flushDuration("leave", true);
    };
    document.addEventListener("visibilitychange", visibilityChanged);
    window.addEventListener("pagehide", pageHidden);
    return () => {
      document.removeEventListener("visibilitychange", visibilityChanged);
      window.removeEventListener("pagehide", pageHidden);
      pageHidden();
    };
  }, [beginSession, cardSlug, enabled, flushDuration, sendPageView]);

  return { trackPage, trackAction };
}
