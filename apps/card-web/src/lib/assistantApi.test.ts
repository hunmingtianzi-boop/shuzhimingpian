import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  createAssistantIdempotencyKey,
  getAssistantSessionStorageKey,
  ensurePublicVisitorSession,
  parseAssistantEventStream,
  prewarmAssistantSession,
  markVisitorSessionBackground,
  recordPublicCardAction,
  resumeVisitorSession,
  streamAssistantMessage,
  type AssistantStreamEvent,
} from "./assistantApi";
import { getProfileLinkStorageKey } from "./profileLink";

class MemoryStorage implements Storage {
  private readonly values = new Map<string, string>();

  get length() {
    return this.values.size;
  }

  clear() {
    this.values.clear();
  }

  getItem(key: string) {
    return this.values.get(key) ?? null;
  }

  key(index: number) {
    return [...this.values.keys()][index] ?? null;
  }

  removeItem(key: string) {
    this.values.delete(key);
  }

  setItem(key: string, value: string) {
    this.values.set(key, value);
  }
}

function chunkedStream(text: string) {
  const bytes = new TextEncoder().encode(text);
  const chunkSizes = [1, 2, 7, 3, 11, 4, 5];

  return new ReadableStream<Uint8Array>({
    start(controller) {
      let offset = 0;
      let chunkIndex = 0;
      while (offset < bytes.length) {
        const end = Math.min(
          offset + chunkSizes[chunkIndex % chunkSizes.length],
          bytes.length,
        );
        controller.enqueue(bytes.slice(offset, end));
        offset = end;
        chunkIndex += 1;
      }
      controller.close();
    },
  });
}

function streamResponse(events: string) {
  return new Response(chunkedStream(events), {
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
  });
}

function jsonResponse(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function completedStream(answer = "可以") {
  return [
    'event: message.started\ndata: {"message_id":"message-1","request_id":"request-1"}\n\n',
    `event: message.delta\ndata: ${JSON.stringify({ text: answer })}\n\n`,
    'event: message.completed\ndata: {"message_id":"message-1","finish_reason":"stop","lead_prompt":false}\n\n',
  ].join("");
}

describe("assistant API", () => {
  beforeEach(() => {
    vi.stubEnv("VITE_API_BASE_URL", "https://api.example.test/api/v1/");
    vi.stubGlobal("sessionStorage", new MemoryStorage());
    vi.stubGlobal("localStorage", new MemoryStorage());
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("generates an RFC 4122 v4 idempotency key when randomUUID is unavailable", () => {
    const getRandomValues = vi.fn((values: Uint8Array) => {
      values.forEach((_, index) => {
        values[index] = index;
      });
      return values;
    });
    vi.stubGlobal("crypto", { getRandomValues });

    expect(createAssistantIdempotencyKey()).toBe(
      "00010203-0405-4607-8809-0a0b0c0d0e0f",
    );
    expect(getRandomValues).toHaveBeenCalledOnce();
  });

  it("rotates the persisted visit only after the background grace window", () => {
    const sessionKey = getAssistantSessionStorageKey("tuozhe");
    sessionStorage.setItem(sessionKey, JSON.stringify({ visitId: "visit-1" }));

    markVisitorSessionBackground("tuozhe", 1_000);
    expect(resumeVisitorSession("tuozhe", 10_999)).toBe(false);
    expect(sessionStorage.getItem(sessionKey)).not.toBeNull();

    markVisitorSessionBackground("tuozhe", 20_000);
    expect(resumeVisitorSession("tuozhe", 55_000)).toBe(true);
    expect(sessionStorage.getItem(sessionKey)).toBeNull();
  });

  it("records a real cta click against the current public visit", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse({
        data: {
          visit_id: "visit-action",
          visitor_session_token: "visitor-action-token",
          expires_at: "2099-01-01T00:00:00Z",
        },
      }))
      .mockResolvedValueOnce(jsonResponse({
        data: {
          id: "event-action",
          event_type: "cta_click",
          occurred_at: "2026-08-08T00:00:00Z",
        },
      }, 201));
    vi.stubGlobal("fetch", fetchMock);

    await recordPublicCardAction({
      cardSlug: "tenant-a",
      actionId: "conference-link",
      actionTitle: "世界会展大会",
      targetType: "external_url",
      companyId: "company-a",
      policyVersions: {
        privacy: "privacy-v3",
        chatNotice: "chat-v5",
        leadConsent: "lead-v2",
        profilePersonalization: "profile-v1",
      },
    });

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "https://api.example.test/api/v1/public/cards/tenant-a/visits",
      "https://api.example.test/api/v1/public/cards/tenant-a/visits/visit-action/events",
    ]);
    const eventInit = fetchMock.mock.calls[1][1]!;
    expect(eventInit.headers).toMatchObject({
      Authorization: "Bearer visitor-action-token",
    });
    expect(JSON.parse(String(eventInit.body))).toMatchObject({
      event_type: "cta_click",
      object_type: "card",
      object_id: "conference-link",
      metadata: {
        action_title: "世界会展大会",
        target_type: "external_url",
      },
    });
  });

  it("parses CRLF SSE frames and UTF-8 data split across arbitrary chunks", async () => {
    const rawEvents = [
      ": heartbeat\r\n\r\n",
      'event: message.started\r\ndata: {"message_id":"message-1","request_id":"request-1"}\r\n\r\n',
      'event: message.delta\r\ndata: {"text":""}\r\n\r\n',
      'event: message.delta\r\ndata: {"text":"你好"}\r\n\r\n',
      'event: message.citation\r\ndata: {"citation_id":"source-1","label":"产品手册","source_type":"document","url":"https://example.test/one"}\r\n\r\n',
      'event: message.citation\r\ndata: {"citation_id":"source-2","label":"服务说明","source_type":"faq"}\r\n\r\n',
      'event: message.completed\r\ndata: {"message_id":"message-1","finish_reason":"stop","lead_prompt":true}\r\n\r\n',
    ].join("");
    const received: AssistantStreamEvent[] = [];

    await parseAssistantEventStream(chunkedStream(rawEvents), (event) => {
      received.push(event);
    });

    expect(received.map((event) => event.type)).toEqual([
      "started",
      "delta",
      "delta",
      "citation",
      "citation",
      "completed",
    ]);
    expect(
      received
        .filter((event) => event.type === "delta")
        .map((event) => event.text)
        .join(""),
    ).toBe("你好");
    expect(
      received
        .filter((event) => event.type === "citation")
        .map((event) => event.citation.label),
    ).toEqual(["产品手册", "服务说明"]);
  });

  it("runs the full public visit-to-stream flow and reuses the tenant session", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        jsonResponse({
          data: {
            policy_versions: {
              privacy: "privacy-v3",
              chat_notice: "chat-v5",
              lead_consent: "lead-v2",
              profile_personalization: "profile-v1",
            },
            company: { id: "company-a" },
          },
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          data: {
            visit_id: "visit-1",
            visitor_session_token: "visitor-token",
            expires_at: "2099-01-01T00:00:00Z",
          },
        }),
      )
      .mockResolvedValueOnce(jsonResponse({ data: { recorded: true } }))
      .mockResolvedValueOnce(
        jsonResponse({
          data: {
            id: "conversation-1",
            status: "active",
            created_at: "2026-07-10T00:00:00Z",
          },
        }),
      )
      .mockResolvedValueOnce(streamResponse(completedStream("第一条回答")));
    vi.stubGlobal("fetch", fetchMock);
    const firstEvents: AssistantStreamEvent[] = [];

    await streamAssistantMessage({
      cardSlug: "tenant-a",
      content: "你们提供什么服务？",
      idempotencyKey: "00000000-0000-4000-8000-000000000099",
      onEvent: (event) => firstEvents.push(event),
    });

    expect(fetchMock).toHaveBeenCalledTimes(5);
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "https://api.example.test/api/v1/public/cards/tenant-a",
      "https://api.example.test/api/v1/public/cards/tenant-a/visits",
      "https://api.example.test/api/v1/public/cards/tenant-a/consents",
      "https://api.example.test/api/v1/public/cards/tenant-a/conversations",
      "https://api.example.test/api/v1/public/conversations/conversation-1/messages:stream",
    ]);

    const visitInit = fetchMock.mock.calls[1][1]!;
    expect(JSON.parse(String(visitInit.body))).toEqual({
      source: "card_web",
      privacy_notice_version: "privacy-v3",
    });
    expect((visitInit.headers as Record<string, string>)["Idempotency-Key"]).toMatch(
      /^[0-9a-f-]{36}$/i,
    );

    const consentInit = fetchMock.mock.calls[2][1]!;
    expect(consentInit.headers).toMatchObject({
      Authorization: "Bearer visitor-token",
    });
    expect(JSON.parse(String(consentInit.body))).toEqual({
      scope: "chat_notice",
      policy_version: "chat-v5",
      granted: true,
    });

    const streamInit = fetchMock.mock.calls[4][1]!;
    expect(streamInit.headers).toMatchObject({
      Accept: "text/event-stream",
      Authorization: "Bearer visitor-token",
      "Idempotency-Key": "00000000-0000-4000-8000-000000000099",
    });
    expect(JSON.parse(String(streamInit.body))).toEqual({
      content: "你们提供什么服务？",
    });
    expect(firstEvents.some((event) => event.type === "completed")).toBe(true);

    expect(
      JSON.parse(
        sessionStorage.getItem(getAssistantSessionStorageKey("tenant-a")) ?? "{}",
      ),
    ).toMatchObject({
      token: "visitor-token",
      conversationId: "conversation-1",
      privacyVersion: "privacy-v3",
      chatNoticeVersion: "chat-v5",
    });

    fetchMock.mockClear();
    fetchMock.mockResolvedValueOnce(streamResponse(completedStream("第二条回答")));

    await streamAssistantMessage({
      cardSlug: "tenant-a",
      content: "第二个问题",
      onEvent: () => undefined,
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe(
      "https://api.example.test/api/v1/public/conversations/conversation-1/messages:stream",
    );
  });

  it("prewarms the complete assistant session from card context without refetching it", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        jsonResponse({
          data: {
            visit_id: "visit-warm",
            visitor_session_token: "visitor-token-warm",
            expires_at: "2099-01-01T00:00:00Z",
          },
        }),
      )
      .mockResolvedValueOnce(jsonResponse({ data: { recorded: true } }))
      .mockResolvedValueOnce(
        jsonResponse({
          data: {
            id: "conversation-warm",
            status: "active",
            created_at: "2026-07-20T00:00:00Z",
          },
        }),
      );
    vi.stubGlobal("fetch", fetchMock);

    await prewarmAssistantSession({
      cardSlug: "tenant-warm",
      companyId: "company-warm",
      policyVersions: {
        privacy: "privacy-v3",
        chatNotice: "chat-v5",
        leadConsent: "lead-v2",
        profilePersonalization: "profile-v1",
      },
    });

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "https://api.example.test/api/v1/public/cards/tenant-warm/visits",
      "https://api.example.test/api/v1/public/cards/tenant-warm/consents",
      "https://api.example.test/api/v1/public/cards/tenant-warm/conversations",
    ]);
    expect(
      JSON.parse(
        sessionStorage.getItem(getAssistantSessionStorageKey("tenant-warm")) ?? "{}",
      ),
    ).toMatchObject({
      token: "visitor-token-warm",
      conversationId: "conversation-warm",
    });
  });

  it("links a new visit only with the matching company token and persists rotation", async () => {
    localStorage.setItem(getProfileLinkStorageKey("company-a"), "profile-token-a-old");
    localStorage.setItem(getProfileLinkStorageKey("company-b"), "profile-token-b");
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValueOnce(
      jsonResponse({
        data: {
          visit_id: "visit-linked",
          visitor_session_token: "short-session-token",
          profile_link_token: "profile-token-a-rotated",
          expires_at: "2099-01-01T00:00:00Z",
        },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await ensurePublicVisitorSession({
      cardSlug: "card-a",
      companyId: "company-a",
      policyVersions: {
        privacy: "privacy-v1",
        chatNotice: "chat-v1",
        leadConsent: "lead-v1",
        profilePersonalization: "profile-v1",
      },
    });

    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({
      source: "card_web",
      privacy_notice_version: "privacy-v1",
      profile_link_token: "profile-token-a-old",
    });
    expect(localStorage.getItem(getProfileLinkStorageKey("company-a"))).toBe(
      "profile-token-a-rotated",
    );
    expect(localStorage.getItem(getProfileLinkStorageKey("company-b"))).toBe(
      "profile-token-b",
    );
    expect(localStorage.getItem(getAssistantSessionStorageKey("card-a"))).toBeNull();
    expect(sessionStorage.getItem(getAssistantSessionStorageKey("card-a"))).toContain(
      "short-session-token",
    );
  });

  it("forgets a rejected profile token when visit creation silently degrades", async () => {
    localStorage.setItem(getProfileLinkStorageKey("company-a"), "rejected-token");
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockResolvedValueOnce(
        jsonResponse({
          data: {
            visit_id: "visit-new",
            visitor_session_token: "new-short-session",
            profile_link_token: null,
            expires_at: "2099-01-01T00:00:00Z",
          },
        }),
      ),
    );

    await ensurePublicVisitorSession({
      cardSlug: "card-a",
      companyId: "company-a",
      policyVersions: {
        privacy: "privacy-v1",
        chatNotice: "chat-v1",
        leadConsent: "lead-v1",
        profilePersonalization: "profile-v1",
      },
    });

    expect(localStorage.getItem(getProfileLinkStorageKey("company-a"))).toBeNull();
  });

  it("surfaces retryable message.error frames after notifying the consumer", async () => {
    const events: AssistantStreamEvent[] = [];
    const promise = parseAssistantEventStream(
      chunkedStream(
        'event: message.error\ndata: {"code":"MODEL_BUSY","retryable":true,"request_id":"request-9"}\n\n',
      ),
      (event) => events.push(event),
    );

    await expect(promise).rejects.toMatchObject({
      code: "MODEL_BUSY",
      retryable: true,
      requestId: "request-9",
    });
    expect(events).toEqual([
      {
        type: "error",
        code: "MODEL_BUSY",
        retryable: true,
        requestId: "request-9",
      },
    ]);
  });

  it("forgets an expired server conversation so the next question can create a new one", async () => {
    const sessionKey = getAssistantSessionStorageKey("tenant-a");
    sessionStorage.setItem(
      sessionKey,
      JSON.stringify({
        token: "visitor-token",
        expiresAt: "2099-01-01T00:00:00Z",
        privacyVersion: "privacy-v3",
        chatNoticeVersion: "chat-v5",
        conversationId: "conversation-expired",
      }),
    );
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockResolvedValueOnce(
        jsonResponse(
          {
            error: {
              code: "CONVERSATION_EXPIRED",
              message: "会话已过期。",
              retryable: true,
            },
          },
          410,
        ),
      ),
    );

    await expect(
      streamAssistantMessage({
        cardSlug: "tenant-a",
        content: "继续介绍它的第二项服务",
        onEvent: () => undefined,
      }),
    ).rejects.toMatchObject({
      code: "CONVERSATION_EXPIRED",
      status: 410,
    });
    expect(sessionStorage.getItem(sessionKey)).toBeNull();
  });
});
