import {
  ArrowUp,
  Buildings,
  CaretRight,
  ChatCircleDots,
  LinkSimple,
  PaperPlaneTilt,
  Robot,
  Sparkle,
  X,
} from "@phosphor-icons/react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useLayoutEffect,
  useRef,
  useState,
} from "react";

import type { AssistantConfig } from "../domain/card";
import {
  AssistantApiError,
  createAssistantIdempotencyKey,
  isAssistantApiConfigured,
  streamAssistantMessage,
  type AssistantCitation,
} from "../lib/assistantApi";
import {
  matchAssistantRelatedSections,
  type AssistantRelatedSection,
} from "../lib/assistantRelatedSections";
import { lockBodyScroll } from "../lib/bodyScrollLock";
import { findKnowledge } from "../lib/knowledge";
import { MarkdownMessage } from "./MarkdownMessage";

type Message = {
  id: number;
  role: "assistant" | "user";
  text: string;
  source?: string;
  citations?: AssistantCitation[];
  relatedSectionIds?: string[];
};

type RequestFailure = {
  question: string;
  idempotencyKey: string;
  assistantMessageId: number;
  retryable: boolean;
  message: string;
};

export type AIAssistantHandle = {
  open: () => void;
  openWithQuestion: (question: string) => void;
};

type AIAssistantProps = {
  config: AssistantConfig;
  cardSlug: string;
  onLeadPrompt?: () => void;
  relatedSections?: AssistantRelatedSection[];
  onOpenRelatedSection?: (targetId: string) => void;
};

function requestErrorMessage(error: unknown) {
  if (!(error instanceof AssistantApiError)) {
    return "AI 服务暂时无法回答，请检查网络后重试。";
  }
  if (error.status === 401 || error.status === 403) {
    return "访客会话已失效，请重试以重新连接。";
  }
  if (error.status === 429) {
    return "当前咨询较多，请稍后重试。";
  }
  if (error.status === 503 || error.code === "NETWORK_ERROR") {
    return "AI 服务暂时不可用，请稍后重试。";
  }
  return "本次回答未完成，请稍后重试。";
}

export const AIAssistant = forwardRef<
  AIAssistantHandle,
  AIAssistantProps
>(function AIAssistant(
  {
    config,
    cardSlug,
    onLeadPrompt,
    relatedSections = [],
    onOpenRelatedSection,
  }: AIAssistantProps,
  ref,
) {
  const apiEnabled = isAssistantApiConfigured();
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>(() => [
    apiEnabled
      ? {
          id: 1,
          role: "assistant",
          text: `你好，我是${config.title}。我会基于企业已发布资料生成回答，并附上可追溯来源。`,
          source: "企业已发布知识库",
        }
      : {
          id: 1,
          role: "assistant",
          text: config.initialMessage.text,
          source: config.initialMessage.source,
        },
  ]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [pendingQuestion, setPendingQuestion] = useState<string | null>(null);
  const [requestFailure, setRequestFailure] = useState<RequestFailure | null>(null);
  const shouldReduceMotion = useReducedMotion();
  const nextId = useRef(2);
  const inputRef = useRef<HTMLInputElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLElement>(null);
  const launcherRef = useRef<HTMLButtonElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const timerRef = useRef<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const activeRequestTokenRef = useRef<symbol | null>(null);
  const mountedRef = useRef(true);
  const scrollUnlockRef = useRef<(() => void) | null>(null);
  const isOpenRef = useRef(isOpen);
  isOpenRef.current = isOpen;

  const releaseScrollLock = useCallback(() => {
    scrollUnlockRef.current?.();
    scrollUnlockRef.current = null;
  }, []);

  useLayoutEffect(() => {
    if (isOpen && !scrollUnlockRef.current) {
      scrollUnlockRef.current = lockBodyScroll();
    }
  }, [isOpen]);

  useEffect(
    () => () => {
      releaseScrollLock();
    },
    [releaseScrollLock],
  );

  const cancelActiveRequest = useCallback(() => {
    if (timerRef.current) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    abortRef.current?.abort();
    abortRef.current = null;
    activeRequestTokenRef.current = null;
  }, []);

  const closeAssistant = useCallback(() => {
    cancelActiveRequest();
    setPendingQuestion(null);
    setIsLoading(false);
    setIsOpen(false);
  }, [cancelActiveRequest]);

  useEffect(() => {
    if (!isOpen) return undefined;

    previousFocusRef.current = document.activeElement as HTMLElement | null;
    const focusTimer = window.setTimeout(() => inputRef.current?.focus(), 80);

    const handleDialogKeys = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        closeAssistant();
        return;
      }

      if (event.key !== "Tab" || !panelRef.current) return;
      const focusable = Array.from(
        panelRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), input:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])',
        ),
      );
      if (focusable.length === 0) return;

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    window.addEventListener("keydown", handleDialogKeys);
    return () => {
      window.clearTimeout(focusTimer);
      cancelActiveRequest();
      window.removeEventListener("keydown", handleDialogKeys);
      const focusTarget = previousFocusRef.current ?? launcherRef.current;
      window.setTimeout(() => focusTarget?.focus(), 0);
    };
  }, [cancelActiveRequest, closeAssistant, isOpen]);

  useEffect(() => {
    const container = scrollRef.current;
    if (!container) return;
    if (typeof container.scrollTo === "function") {
      container.scrollTo({
        top: container.scrollHeight,
        behavior: shouldReduceMotion ? "auto" : "smooth",
      });
    } else {
      container.scrollTop = container.scrollHeight;
    }
  }, [messages, isLoading, shouldReduceMotion]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      cancelActiveRequest();
    };
  }, [cancelActiveRequest]);

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
      if (!question || activeRequestTokenRef.current) return;

      const requestToken = Symbol("assistant-request");
      activeRequestTokenRef.current = requestToken;
      const finishRequest = () => {
        if (activeRequestTokenRef.current !== requestToken) return;
        activeRequestTokenRef.current = null;
        setIsLoading(false);
      };

      const appendUser = options?.appendUser ?? true;
      const userMessage: Message | undefined = appendUser
        ? { id: nextId.current++, role: "user", text: question }
        : undefined;
      setInput("");
      setRequestFailure(null);
      setIsLoading(true);

      if (!apiEnabled) {
        if (userMessage) setMessages((current) => [...current, userMessage]);
        timerRef.current = window.setTimeout(() => {
          const result = findKnowledge(question, config.knowledgeBase, config.fallback);
          const assistantMessage: Message = {
            id: nextId.current++,
            role: "assistant",
            text: result.answer,
            source: result.source,
            relatedSectionIds: matchAssistantRelatedSections(
              result.answer,
              undefined,
              relatedSections,
            ).map((section) => section.id),
          };
          setMessages((current) => [...current, assistantMessage]);
          finishRequest();
          timerRef.current = null;
        }, shouldReduceMotion ? 0 : 520);
        return;
      }

      const assistantMessageId = options?.assistantMessageId ?? nextId.current++;
      const assistantMessage: Message = {
        id: assistantMessageId,
        role: "assistant",
        text: "",
        citations: [],
      };
      setMessages((current) => {
        const withoutPreviousAttempt = current.filter(
          (message) => message.id !== assistantMessageId,
        );
        return [
          ...withoutPreviousAttempt,
          ...(userMessage ? [userMessage] : []),
          assistantMessage,
        ];
      });

      let idempotencyKey: string;
      try {
        idempotencyKey =
          options?.idempotencyKey ?? createAssistantIdempotencyKey();
      } catch (error) {
        setMessages((current) =>
          current.filter((message) => message.id !== assistantMessageId),
        );
        setRequestFailure({
          question,
          assistantMessageId,
          idempotencyKey: "",
          retryable: false,
          message: requestErrorMessage(error),
        });
        finishRequest();
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
                ? { ...message, relatedSectionIds }
                : message,
            ));
          }
        },
      })
        .then(() => {
          if (!mountedRef.current || !shouldOpenLead || !onLeadPrompt) return;
          setIsOpen(false);
          window.setTimeout(onLeadPrompt, 0);
        })
        .catch((error: unknown) => {
          if (!mountedRef.current) return;
          if (controller.signal.aborted) {
            setMessages((current) =>
              current.filter(
                (message) =>
                  message.id !== assistantMessageId ||
                  message.text ||
                  (message.citations?.length ?? 0) > 0,
              ),
            );
            return;
          }

          setMessages((current) =>
            current.filter(
              (message) =>
                message.id !== assistantMessageId ||
                message.text ||
                (message.citations?.length ?? 0) > 0,
            ),
          );
          setRequestFailure({
            question,
            idempotencyKey,
            assistantMessageId,
            retryable:
              error instanceof AssistantApiError ? error.retryable : true,
            message: requestErrorMessage(error),
          });
        })
        .finally(() => {
          if (!mountedRef.current) return;
          if (abortRef.current === controller) abortRef.current = null;
          finishRequest();
        });
    },
    [
      apiEnabled,
      cardSlug,
      config.fallback,
      config.knowledgeBase,
      relatedSections,
      shouldReduceMotion,
      onLeadPrompt,
    ],
  );

  useEffect(() => {
    if (!isOpen || !pendingQuestion) return;
    const question = pendingQuestion;
    setPendingQuestion(null);
    ask(question);
  }, [ask, isOpen, pendingQuestion]);

  useImperativeHandle(
    ref,
    () => ({
      open: () => setIsOpen(true),
      openWithQuestion: (question: string) => {
        setIsOpen(true);
        setPendingQuestion(question);
      },
    }),
    [ask],
  );

  const quickQuestions = config.quickQuestionIds
    .map((id) => config.knowledgeBase.find((item) => item.id === id))
    .filter((item) => item !== undefined);

  return (
    <>
      <button
        className="assistant-launcher"
        ref={launcherRef}
        type="button"
        onClick={() => setIsOpen(true)}
        aria-label={config.launcherAriaLabel}
      >
        <span className="assistant-launcher-icon">
          <ChatCircleDots size={22} weight="fill" aria-hidden="true" />
        </span>
        <span className="assistant-launcher-copy">
          <small>{config.launcherKicker}</small>
          <strong>{config.launcherLabel}</strong>
        </span>
      </button>

      <AnimatePresence
        onExitComplete={() => {
          if (!isOpenRef.current) releaseScrollLock();
        }}
      >
        {isOpen && (
          <>
            <motion.button
              className="assistant-backdrop"
              type="button"
              aria-label={config.labels.closeBackdrop}
              onClick={closeAssistant}
              initial={shouldReduceMotion ? false : { opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={shouldReduceMotion ? undefined : { opacity: 0 }}
              transition={{ duration: 0.14, ease: "easeOut" }}
            />
            <motion.aside
              ref={panelRef}
              className="assistant-panel"
              role="dialog"
              aria-modal="true"
              aria-labelledby="assistant-title"
              initial={shouldReduceMotion ? false : { opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={shouldReduceMotion ? undefined : { opacity: 0 }}
              transition={{ duration: 0.16, ease: "easeOut" }}
            >
              <header className="assistant-header">
                <div className="assistant-identity">
                  <span className="assistant-avatar" aria-hidden="true">
                    <Robot size={22} weight="duotone" />
                  </span>
                  <div>
                    <div className="assistant-title-row">
                      <h2 id="assistant-title">{config.title}</h2>
                      <span className="assistant-status">
                        {apiEnabled ? "在线" : config.status}
                      </span>
                    </div>
                    <p>{apiEnabled ? "企业知识库 · 实时 AI 回答" : config.subtitle}</p>
                  </div>
                </div>
                <button
                  className="icon-button"
                  type="button"
                  onClick={closeAssistant}
                  aria-label={config.labels.closeButton}
                >
                  <X size={20} aria-hidden="true" />
                </button>
              </header>

              <div className="assistant-messages" ref={scrollRef} aria-live="polite">
                {messages.map((message) => {
                  const matchedSections = message.role === "assistant" && onOpenRelatedSection
                    ? relatedSections.filter((section) => message.relatedSectionIds?.includes(section.id))
                    : [];
                  return (
                    <div className={`message message-${message.role}`} key={message.id}>
                      {message.text && <MarkdownMessage content={message.text} />}
                      {message.source && (
                        <small>
                          <LinkSimple size={13} aria-hidden="true" />
                          {config.labels.sourcePrefix}
                          {message.source}
                        </small>
                      )}
                      {message.citations?.map((citation) => (
                        <small key={citation.id}>
                          <LinkSimple size={13} aria-hidden="true" />
                          {config.labels.sourcePrefix}
                          {citation.label}
                        </small>
                      ))}
                      {matchedSections.length > 0 && (
                        <div className="assistant-related-sections" aria-label="回答相关内容">
                          <span>
                            <Buildings size={14} weight="duotone" aria-hidden="true" />
                            回答中提到的内容
                          </span>
                          {matchedSections.map((section) => (
                            <button
                              key={section.id}
                              type="button"
                              onClick={() => {
                                closeAssistant();
                                window.setTimeout(() => onOpenRelatedSection?.(section.targetId), 0);
                              }}
                              aria-label={`查看相关内容：${section.title}`}
                            >
                              <span>
                                <strong>{section.title}</strong>
                                <small>{section.description}</small>
                              </span>
                              <CaretRight size={16} aria-hidden="true" />
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}

                {messages.length === 1 && quickQuestions.length > 0 && (
                  <div className="quick-questions" aria-label={config.labels.quickQuestions}>
                    <span>
                      <Sparkle size={14} weight="fill" aria-hidden="true" />
                      {config.labels.quickQuestionsIntro}
                    </span>
                    {quickQuestions.map((item) => (
                      <button
                        type="button"
                        key={item.id}
                        onClick={() => ask(item.shortQuestion)}
                      >
                        {item.shortQuestion}
                      </button>
                    ))}
                  </div>
                )}

                {isLoading && (
                  <div
                    className="message message-assistant message-loading"
                    aria-label={config.labels.loading}
                  >
                    <i />
                    <i />
                    <i />
                  </div>
                )}

                {requestFailure && (
                  <div className="assistant-request-error" role="alert">
                    <span>{requestFailure.message}</span>
                    {requestFailure.retryable && requestFailure.idempotencyKey && (
                      <button
                        type="button"
                        onClick={() => {
                          const failedRequest = requestFailure;
                          ask(failedRequest.question, {
                            appendUser: false,
                            assistantMessageId: failedRequest.assistantMessageId,
                            idempotencyKey: failedRequest.idempotencyKey,
                          });
                        }}
                      >
                        重试
                      </button>
                    )}
                  </div>
                )}
              </div>

              <form
                className="assistant-composer"
                onSubmit={(event) => {
                  event.preventDefault();
                  ask(input);
                }}
              >
                <label htmlFor="assistant-question" className="sr-only">
                  {config.labels.input}
                </label>
                <input
                  id="assistant-question"
                  ref={inputRef}
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                  placeholder={config.labels.placeholder}
                  autoComplete="off"
                  maxLength={2000}
                />
                <button
                  type="submit"
                  disabled={!input.trim() || isLoading}
                  aria-label={config.labels.send}
                >
                  <ArrowUp size={18} weight="bold" aria-hidden="true" />
                </button>
              </form>
              {onLeadPrompt && (
                <button
                  className="assistant-lead-action"
                  type="button"
                  onClick={() => {
                    closeAssistant();
                    onLeadPrompt();
                  }}
                >
                  <PaperPlaneTilt size={16} aria-hidden="true" />
                  需要人工联系？留下合作需求
                </button>
              )}
              <p className="assistant-disclaimer">
                {config.disclaimer}
              </p>
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </>
  );
});
