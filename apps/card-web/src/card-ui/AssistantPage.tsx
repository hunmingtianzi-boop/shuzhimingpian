import {
  ArrowClockwise,
  ArrowUp,
  Buildings,
  CaretRight,
  ChatCircleDots,
  Cube,
  FolderStar,
  Handshake,
  LinkSimple,
  Sparkle,
  Stack,
} from "@phosphor-icons/react";
import { motion, useReducedMotion } from "motion/react";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
} from "react";

import { MarkdownMessage } from "../components/MarkdownMessage";
import type {
  AssistantConfig,
  AssistantRecommendation,
  ResponsiveMediaAsset,
} from "../domain/card";
import {
  AssistantApiError,
  clearAssistantSession,
  createAssistantIdempotencyKey,
  getActiveAssistantConversationId,
  getAssistantSessionStorageKey,
  isAssistantApiConfigured,
  streamAssistantMessage,
  type AssistantCitation,
} from "../lib/assistantApi";
import { findKnowledge } from "../lib/knowledge";

type ChatMessage = {
  id: number;
  role: "assistant" | "user";
  text: string;
  source?: string;
  citations?: AssistantCitation[];
  complete?: boolean;
  relatedSectionIds?: string[];
};

export type AssistantRelatedSection = {
  id: string;
  targetId: string;
  title: string;
  description: string;
  keywords: string[];
};

type RequestFailure = {
  question: string;
  idempotencyKey: string;
  assistantMessageId: number;
  retryable: boolean;
  message: string;
};

export type PendingAssistantQuestion = {
  id: number;
  text: string;
};

function failureMessage(error: unknown) {
  if (!(error instanceof AssistantApiError)) return "AI 服务暂时无法回答，请检查网络后重试。";
  if ([401, 403, 404, 410].includes(error.status ?? 0)) {
    return "访客会话已失效，请重试以重新连接。";
  }
  if (error.status === 429) return "当前咨询较多，请稍后重试。";
  if (error.status === 503 || error.code === "NETWORK_ERROR") return "AI 服务暂时不可用，请稍后重试。";
  return "本次回答未完成，请稍后重试。";
}

function historyKey(cardSlug: string) {
  return `${getAssistantSessionStorageKey(cardSlug)}:visible-messages`;
}

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

function readMessageHistory(cardSlug: string, apiEnabled: boolean): ChatMessage[] | undefined {
  try {
    const raw = window.sessionStorage.getItem(historyKey(cardSlug));
    if (!raw) return undefined;
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return undefined;
    const stored = parsed as { conversationId?: unknown; messages?: unknown };
    const expectedConversationId = apiEnabled
      ? getActiveAssistantConversationId(cardSlug)
      : "static";
    if (
      !expectedConversationId ||
      stored.conversationId !== expectedConversationId ||
      !Array.isArray(stored.messages)
    ) {
      window.sessionStorage.removeItem(historyKey(cardSlug));
      return undefined;
    }
    const messages = stored.messages.filter((item): item is ChatMessage => {
      if (!item || typeof item !== "object") return false;
      const candidate = item as Partial<ChatMessage>;
      return (
        typeof candidate.id === "number" &&
        (candidate.role === "assistant" || candidate.role === "user") &&
        typeof candidate.text === "string"
      );
    });
    return messages.length
      ? messages.slice(-40).map((message) => ({ ...message, complete: message.complete !== false }))
      : undefined;
  } catch {
    return undefined;
  }
}

function writeMessageHistory(cardSlug: string, messages: ChatMessage[], apiEnabled: boolean) {
  try {
    const conversationId = apiEnabled
      ? getActiveAssistantConversationId(cardSlug)
      : "static";
    if (!conversationId || !messages.some((message) => message.role === "user")) return;
    window.sessionStorage.setItem(
      historyKey(cardSlug),
      JSON.stringify({ conversationId, messages: messages.slice(-40) }),
    );
  } catch {
    // The assistant stays usable when browser storage is blocked.
  }
}

function clearMessageHistory(cardSlug: string) {
  try {
    window.sessionStorage.removeItem(historyKey(cardSlug));
  } catch {
    // Ignore unavailable or blocked session storage.
  }
}

function contextualStaticQuestion(question: string, messages: ChatMessage[]) {
  if (!/^(?:那|那么|还有|再|继续|这个|那个|它|这些|那些|第二个|上面|前面)/.test(question)) {
    return question;
  }
  const recent = messages
    .filter((message) => message.text.trim())
    .slice(-2)
    .map((message) => message.text.trim());
  return recent.length ? `${recent.join("\n")}\n${question}` : question;
}

function ResponsiveImage({ asset, className }: { asset: ResponsiveMediaAsset; className?: string }) {
  return (
    <img
      className={className}
      src={asset.src}
      srcSet={asset.srcSet}
      sizes={asset.sizes}
      width={asset.width}
      height={asset.height}
      alt={asset.alt}
      decoding="async"
    />
  );
}

export function AssistantPage({
  config,
  cardSlug,
  assistantVisual,
  recommendations,
  questionIds,
  welcomeMessage,
  displayName,
  disclosure,
  suggestedQuestions,
  liveAvailable,
  pendingQuestion,
  isActive,
  onLead,
  relatedSections,
  onOpenEnterpriseSection,
}: {
  config: AssistantConfig;
  cardSlug: string;
  assistantVisual?: ResponsiveMediaAsset;
  recommendations: AssistantRecommendation[];
  questionIds?: string[];
  welcomeMessage?: string;
  displayName?: string;
  disclosure?: string;
  suggestedQuestions?: string[];
  liveAvailable: boolean;
  pendingQuestion?: PendingAssistantQuestion;
  isActive: boolean;
  onLead: () => void;
  relatedSections: AssistantRelatedSection[];
  onOpenEnterpriseSection: (targetId: string) => void;
}) {
  const apiEnabled = liveAvailable && isAssistantApiConfigured();
  const assistantName = displayName?.trim() || config.title;
  const reducedMotion = useReducedMotion();
  const initialMessage = useMemo<ChatMessage>(
    () => ({
      id: 1,
      role: "assistant",
      text:
        welcomeMessage?.trim() ||
        (apiEnabled
          ? `你好，我是${assistantName}。我会基于企业已发布资料回答，并尽量提供可追溯来源。`
          : config.initialMessage.text),
      source: apiEnabled ? "企业已发布知识库" : config.initialMessage.source,
      complete: true,
    }),
    [apiEnabled, assistantName, config.initialMessage.source, config.initialMessage.text, welcomeMessage],
  );
  const [messages, setMessages] = useState<ChatMessage[]>(
    () => readMessageHistory(cardSlug, apiEnabled) ?? [initialMessage],
  );
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [requestFailure, setRequestFailure] = useState<RequestFailure | null>(null);
  const nextId = useRef(Math.max(2, ...messages.map((message) => message.id + 1)));
  const abortRef = useRef<AbortController | null>(null);
  const activeRequestRef = useRef<symbol | null>(null);
  const timerRef = useRef<number | null>(null);
  const handledPendingId = useRef<number | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const mountedRef = useRef(true);
  const messagesRef = useRef(messages);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      abortRef.current?.abort();
      if (timerRef.current) window.clearTimeout(timerRef.current);
    };
  }, []);

  useEffect(() => {
    messagesRef.current = messages;
    writeMessageHistory(cardSlug, messages, apiEnabled);
  }, [apiEnabled, cardSlug, messages]);

  useEffect(() => {
    if (!isActive) return;
    const scrollTarget = endRef.current;
    if (!scrollTarget || typeof scrollTarget.scrollIntoView !== "function") return;
    scrollTarget.scrollIntoView({
      behavior: reducedMotion ? "auto" : "smooth",
      block: "nearest",
    });
  }, [isActive, isLoading, messages, reducedMotion, requestFailure]);

  const ask = useCallback(
    (
      rawQuestion: string,
      options?: {
        appendUser?: boolean;
        assistantMessageId?: number;
        idempotencyKey?: string;
      },
    ) => {
      const question = rawQuestion.trim();
      if (!question || activeRequestRef.current) return;

      const requestToken = Symbol("assistant-request");
      activeRequestRef.current = requestToken;
      const finish = () => {
        if (activeRequestRef.current !== requestToken) return;
        activeRequestRef.current = null;
        setIsLoading(false);
      };
      const userMessage =
        options?.appendUser === false
          ? undefined
          : ({ id: nextId.current++, role: "user", text: question, complete: true } satisfies ChatMessage);
      const conversationSnapshot = messagesRef.current;

      setInput("");
      setRequestFailure(null);
      setIsLoading(true);

      if (!apiEnabled) {
        if (userMessage) setMessages((current) => [...current, userMessage]);
        timerRef.current = window.setTimeout(() => {
          const result = findKnowledge(
            contextualStaticQuestion(question, conversationSnapshot),
            config.knowledgeBase,
            config.fallback,
          );
          const relatedSectionIds = matchAssistantRelatedSections(
            result.answer,
            undefined,
            relatedSections,
          ).map((section) => section.id);
          setMessages((current) => [
            ...current,
            {
              id: nextId.current++,
              role: "assistant",
              text: result.answer,
              source: result.source,
              complete: true,
              relatedSectionIds,
            },
          ]);
          timerRef.current = null;
          finish();
        }, reducedMotion ? 0 : 420);
        return;
      }

      const assistantMessageId = options?.assistantMessageId ?? nextId.current++;
      setMessages((current) => [
        ...current.filter((message) => message.id !== assistantMessageId),
        ...(userMessage ? [userMessage] : []),
        { id: assistantMessageId, role: "assistant", text: "", citations: [], complete: false },
      ]);

      let idempotencyKey: string;
      try {
        idempotencyKey = options?.idempotencyKey ?? createAssistantIdempotencyKey();
      } catch (error) {
        setMessages((current) => current.filter((message) => message.id !== assistantMessageId));
        setRequestFailure({
          question,
          assistantMessageId,
          idempotencyKey: "",
          retryable: false,
          message: failureMessage(error),
        });
        finish();
        return;
      }

      const controller = new AbortController();
      abortRef.current = controller;
      let shouldOpenLead = false;
      let answerText = "";
      const answerCitations: AssistantCitation[] = [];
      void streamAssistantMessage({
        cardSlug,
        content: question,
        signal: controller.signal,
        idempotencyKey,
        onEvent: (event) => {
          if (!mountedRef.current) return;
          if (event.type === "delta") {
            answerText += event.text;
            setMessages((current) =>
              current.map((message) =>
                message.id === assistantMessageId
                  ? { ...message, text: message.text + event.text }
                  : message,
              ),
            );
          } else if (event.type === "citation") {
            if (!answerCitations.some((citation) => citation.id === event.citation.id)) {
              answerCitations.push(event.citation);
            }
            setMessages((current) =>
              current.map((message) => {
                if (message.id !== assistantMessageId) return message;
                const citations = message.citations ?? [];
                return citations.some((citation) => citation.id === event.citation.id)
                  ? message
                  : { ...message, citations: [...citations, event.citation] };
              }),
            );
          } else if (event.type === "completed") {
            shouldOpenLead = event.leadPrompt;
            const relatedSectionIds = matchAssistantRelatedSections(
              answerText,
              answerCitations,
              relatedSections,
            ).map((section) => section.id);
            setMessages((current) => current.map((message) =>
              message.id === assistantMessageId
                ? { ...message, complete: true, relatedSectionIds }
                : message,
            ));
          }
        },
      })
        .then(() => {
          if (shouldOpenLead) onLead();
        })
        .catch((error: unknown) => {
          if (!mountedRef.current || controller.signal.aborted) return;
          const sessionExpired = error instanceof AssistantApiError && (
            error.status === 401 ||
            error.status === 403 ||
            error.status === 404 ||
            error.status === 410 ||
            (error.status === 409 && error.code === "POLICY_VERSION_MISMATCH")
          );
          if (sessionExpired) {
            clearMessageHistory(cardSlug);
            setMessages([
              initialMessage,
              ...(userMessage ? [userMessage] : []),
            ]);
          } else {
            setMessages((current) =>
              current.filter(
                (message) =>
                  message.id !== assistantMessageId ||
                  message.text ||
                  (message.citations?.length ?? 0) > 0,
              ),
            );
          }
          setRequestFailure({
            question,
            idempotencyKey,
            assistantMessageId,
            retryable: error instanceof AssistantApiError ? error.retryable : true,
            message: failureMessage(error),
          });
        })
        .finally(() => {
          if (abortRef.current === controller) abortRef.current = null;
          finish();
        });
    },
    [
      apiEnabled,
      cardSlug,
      config.fallback,
      config.knowledgeBase,
      initialMessage,
      onLead,
      reducedMotion,
      relatedSections,
    ],
  );

  useEffect(() => {
    if (!pendingQuestion || handledPendingId.current === pendingQuestion.id) return;
    handledPendingId.current = pendingQuestion.id;
    ask(pendingQuestion.text);
  }, [ask, pendingQuestion]);

  const publishedQuestions = (suggestedQuestions ?? [])
    .map((question) => question.trim())
    .filter((question, index, values) => Boolean(question) && values.indexOf(question) === index)
    .slice(0, 5)
    .map((question, index) => ({
      id: `published-question-${index}`,
      question,
      shortQuestion: question,
    }));
  const quickQuestions = publishedQuestions.length
    ? publishedQuestions
    : (questionIds?.length ? questionIds : config.quickQuestionIds)
      .map((id) => config.knowledgeBase.find((item) => item.id === id))
      .filter((item) => item !== undefined)
      .slice(0, 5);
  const hasConversation = messages.some((message) => message.role === "user");
  const recommendationIcons = [Stack, Handshake, FolderStar];

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    ask(input);
  };

  return (
    <main className="tz-page tz-assistant-page" id="assistant-view">
      <header className="tz-assistant-heading">
        <span className="tz-kicker"><Sparkle weight="fill" aria-hidden="true" /> 智能企业接待</span>
        <h1>{assistantName}</h1>
        <p>智能对话，高效连接，价值共创</p>
      </header>

      {!hasConversation && (
        <>
          <section className="tz-assistant-welcome" aria-labelledby="assistant-welcome-title">
            <div>
              <span className="tz-live-status"><i />{apiEnabled ? "实时在线" : "资料模式"}</span>
              <h2 id="assistant-welcome-title">您好，我是{assistantName}</h2>
              <p>我可以为您介绍业务、项目、成功案例和合作方式。</p>
            </div>
            {assistantVisual ? (
              <ResponsiveImage asset={assistantVisual} className="tz-assistant-robot" />
            ) : (
              <Cube className="tz-assistant-fallback-icon" weight="duotone" aria-hidden="true" />
            )}
          </section>

          <section className="tz-panel tz-question-panel" aria-labelledby="quick-question-title">
            <div className="tz-section-title">
              <div>
                <h2 id="quick-question-title">您可以问我</h2>
              </div>
              <small>基于公开资料</small>
            </div>
            <div className="tz-question-list">
              {quickQuestions.map((item) => (
                <button key={item.id} type="button" onClick={() => ask(item.question)}>
                  <span><ChatCircleDots weight="duotone" aria-hidden="true" /></span>
                  <strong>{item.shortQuestion}</strong>
                  <CaretRight aria-hidden="true" />
                </button>
              ))}
            </div>
          </section>

          {recommendations.length > 0 && (
            <section className="tz-panel tz-recommendation-panel" aria-labelledby="recommendation-title">
              <div className="tz-section-title">
                <div>
                  <h2 id="recommendation-title">热门推荐</h2>
                </div>
              </div>
              <div className="tz-recommendation-grid">
                {recommendations.slice(0, 3).map((item, index) => {
                  const Icon = recommendationIcons[index] ?? Stack;
                  return (
                    <button key={item.title} type="button" onClick={() => ask(item.question)}>
                      <Icon weight="duotone" aria-hidden="true" />
                      <strong>{item.title}</strong>
                      <span>{item.description}</span>
                      <i><CaretRight aria-hidden="true" /></i>
                    </button>
                  );
                })}
              </div>
            </section>
          )}
        </>
      )}

      {hasConversation && (
        <section className="tz-chat" aria-label="AI 对话记录" aria-live="polite">
          <div className="tz-chat-status">
            <span><i />{apiEnabled ? "企业知识库已连接" : "正在使用静态资料"}</span>
            <button
              type="button"
              onClick={() => {
                abortRef.current?.abort();
                activeRequestRef.current = null;
                clearAssistantSession(cardSlug);
                clearMessageHistory(cardSlug);
                setMessages([initialMessage]);
                setRequestFailure(null);
                setIsLoading(false);
              }}
            >
              重新开始
            </button>
          </div>
          {messages.map((message) => {
            const matchedSections = message.role === "assistant" && message.complete !== false
              ? relatedSections.filter((section) => message.relatedSectionIds?.includes(section.id))
              : [];
            return (
              <motion.article
                className={`tz-message tz-message-${message.role}`}
                key={message.id}
                initial={reducedMotion ? false : { opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.2 }}
              >
                {message.text && <MarkdownMessage content={message.text} />}
                {message.source && (
                  <small><LinkSimple aria-hidden="true" />来源：{message.source}</small>
                )}
                {message.citations?.map((citation) =>
                  citation.url ? (
                    <a key={citation.id} href={citation.url} target="_blank" rel="noreferrer noopener">
                      <LinkSimple aria-hidden="true" />来源：{citation.label}
                    </a>
                  ) : (
                    <small key={citation.id}><LinkSimple aria-hidden="true" />来源：{citation.label}</small>
                  ),
                )}
                {matchedSections.length > 0 && (
                  <div className="tz-related-sections" aria-label="相关企业板块">
                    <span><Buildings weight="duotone" aria-hidden="true" />相关企业板块</span>
                    {matchedSections.map((section) => (
                      <button
                        key={section.id}
                        type="button"
                        onClick={() => onOpenEnterpriseSection(section.targetId)}
                        aria-label={`查看企业板块：${section.title}`}
                      >
                        <strong>{section.title}</strong>
                        <small>{section.description}</small>
                        <CaretRight aria-hidden="true" />
                      </button>
                    ))}
                  </div>
                )}
              </motion.article>
            );
          })}
          {isLoading && (
            <div className="tz-message tz-message-assistant tz-message-loading" aria-label="正在生成回答">
              <i /><i /><i />
            </div>
          )}
          {requestFailure && (
            <div className="tz-chat-error" role="alert">
              <span>{requestFailure.message}</span>
              {requestFailure.retryable && requestFailure.idempotencyKey && (
                <button
                  type="button"
                  onClick={() =>
                    ask(requestFailure.question, {
                      appendUser: false,
                      assistantMessageId: requestFailure.assistantMessageId,
                      idempotencyKey: requestFailure.idempotencyKey,
                    })
                  }
                >
                  <ArrowClockwise aria-hidden="true" />重试
                </button>
              )}
            </div>
          )}
          <div ref={endRef} />
        </section>
      )}

      <div className="tz-composer-dock">
        <form onSubmit={submit}>
          <label className="sr-only" htmlFor="tz-assistant-input">向 AI 助手提问</label>
          <input
            id="tz-assistant-input"
            ref={inputRef}
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="请输入您的问题..."
            maxLength={2000}
            autoComplete="off"
          />
          <button type="submit" disabled={!input.trim() || isLoading} aria-label="发送问题">
            <ArrowUp weight="bold" aria-hidden="true" />
          </button>
        </form>
        <p title={disclosure}>{disclosure?.trim() || "内容由 AI 生成，仅供参考"}</p>
      </div>
    </main>
  );
}
