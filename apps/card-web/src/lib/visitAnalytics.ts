import { useCallback, useEffect, useRef } from "react";

import {
  ensureVisitSession,
  recordVisitEvent,
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

  const enqueue = useCallback((operation: () => Promise<void>) => {
    queueRef.current = queueRef.current
      .catch(() => undefined)
      .then(operation)
      .catch(() => undefined);
  }, []);

  const sendPageView = useCallback((page: ActivePage) => {
    const session = sessionRef.current;
    if (!session) return;
    enqueue(() => recordVisitEvent({
      cardSlug,
      session,
      eventType: "page_view",
      objectType: page.objectType,
      objectId: page.objectId,
      metadata: { page_key: page.key, page_title: page.title },
    }));
  }, [cardSlug, enqueue]);

  const flushDuration = useCallback((eventType: "heartbeat" | "leave", keepalive = false) => {
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
    void ensureVisitSession({
      cardSlug,
      companyId,
      policyVersions,
      signal: controller.signal,
    }).then((session) => {
      if (controller.signal.aborted) return;
      sessionRef.current = session;
      const page = activePageRef.current;
      if (page) sendPageView(page);
    }).catch(() => undefined);
    return () => controller.abort();
  }, [cardSlug, companyId, enabled, policyVersions, sendPageView]);

  useEffect(() => {
    if (!enabled) return undefined;
    const visibilityChanged = () => {
      if (document.visibilityState === "hidden") {
        flushDuration("heartbeat", true);
      } else {
        const page = activePageRef.current;
        if (page) {
          page.enteredAt = performance.now();
          sendPageView(page);
        }
      }
    };
    const pageHidden = () => flushDuration("leave", true);
    document.addEventListener("visibilitychange", visibilityChanged);
    window.addEventListener("pagehide", pageHidden);
    return () => {
      document.removeEventListener("visibilitychange", visibilityChanged);
      window.removeEventListener("pagehide", pageHidden);
      pageHidden();
    };
  }, [enabled, flushDuration, sendPageView]);

  return { trackPage, trackAction };
}
