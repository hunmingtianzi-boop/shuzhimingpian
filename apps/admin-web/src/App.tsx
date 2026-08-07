import { Button } from "@fluentui/react-components";
import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { ApiError } from "./api/client";
import { platformApi } from "./api/platformApi";
import type {
  ConfirmPlatformOnboardingInput,
  PlatformLlmProfile as ApiPlatformLlmProfile,
  PlatformOnboardingImportItem,
  PlatformOnboardingSession,
  StartPlatformOnboardingInput,
} from "./api/types";
import { AuthProvider, useAuth } from "./auth/AuthContext";
import {
  adminWorkspaceForUser,
  canAccessAdminWorkspace,
} from "./auth/permissions";
import { AppShell } from "./components/AppShell";
import { BootScreen } from "./components/BootScreen";
import { ResourceState } from "./components/ResourceState";
import { LoginPage } from "./pages/LoginPage";
import type {
  PlatformLlmConnectionResult,
  PlatformLlmCurrentConfig,
  PlatformLlmProfile,
  PlatformLlmProfileInput,
  PlatformLlmReadiness,
} from "./pages/PlatformLlmSettingsPage";
import {
  adminWorkspaceForPath,
  APP_PATHS,
  navigate,
  type AppPath,
  usePathname,
  WECOM_ENTRY_PATH,
} from "./routing";
import { confirmOnboardingWithRecovery } from "./utils/platformOnboarding";

const OverviewPage = lazy(() =>
  import("./pages/OverviewPage").then((module) => ({
    default: module.OverviewPage,
  })),
);
const VisitsPage = lazy(() =>
  import("./pages/VisitsPage").then((module) => ({
    default: module.VisitsPage,
  })),
);
const VisitorProfilesPage = lazy(() =>
  import("./pages/VisitorProfilesPage").then((module) => ({
    default: module.VisitorProfilesPage,
  })),
);
const ConversationsPage = lazy(() =>
  import("./pages/ConversationsPage").then((module) => ({
    default: module.ConversationsPage,
  })),
);
const OpportunitiesPage = lazy(() =>
  import("./pages/OpportunitiesPage").then((module) => ({
    default: module.OpportunitiesPage,
  })),
);
const LeadsPage = lazy(() =>
  import("./pages/LeadsPage").then((module) => ({
    default: module.LeadsPage,
  })),
);
const ExportsPage = lazy(() =>
  import("./pages/ExportsPage").then((module) => ({
    default: module.ExportsPage,
  })),
);
const KnowledgeGapsPage = lazy(() =>
  import("./pages/KnowledgeGapsPage").then((module) => ({
    default: module.KnowledgeGapsPage,
  })),
);
const NotificationsPage = lazy(() =>
  import("./pages/NotificationsPage").then((module) => ({
    default: module.NotificationsPage,
  })),
);
const PrivacyRequestsPage = lazy(() =>
  import("./pages/PrivacyRequestsPage").then((module) => ({
    default: module.PrivacyRequestsPage,
  })),
);
const CompanyProfilePage = lazy(() =>
  import("./pages/CompanyProfilePage").then((module) => ({
    default: module.CompanyProfilePage,
  })),
);
const CompanySetupPage = lazy(() =>
  import("./pages/CompanySetupPage").then((module) => ({
    default: module.CompanySetupPage,
  })),
);
const CardSettingsPage = lazy(() =>
  import("./pages/CardSettingsPage").then((module) => ({
    default: module.CardSettingsPage,
  })),
);
const KnowledgePage = lazy(() =>
  import("./pages/KnowledgePage").then((module) => ({
    default: module.KnowledgePage,
  })),
);
const CardsPage = lazy(() =>
  import("./pages/CardsPage").then((module) => ({
    default: module.CardsPage,
  })),
);
const ProductsPage = lazy(() =>
  import("./pages/CatalogPage").then((module) => ({
    default: module.ProductsPage,
  })),
);
const CaseStudiesPage = lazy(() =>
  import("./pages/CatalogPage").then((module) => ({
    default: module.CaseStudiesPage,
  })),
);
const ForbiddenTopicsPage = lazy(() =>
  import("./pages/ForbiddenTopicsPage").then((module) => ({
    default: module.ForbiddenTopicsPage,
  })),
);
const PlatformEnterprisesPage = lazy(() =>
  import("./pages/PlatformEnterprisesPage").then((module) => ({
    default: module.PlatformEnterprisesPage,
  })),
);
const PlatformOverviewPage = lazy(() =>
  import("./pages/PlatformOverviewPage").then((module) => ({
    default: module.PlatformOverviewPage,
  })),
);
const PlatformLlmSettingsPage = lazy(() =>
  import("./pages/PlatformLlmSettingsPage").then((module) => ({
    default: module.PlatformLlmSettingsPage,
  })),
);
const PlatformOnboardingPage = lazy(() =>
  import("./pages/PlatformOnboardingPage").then((module) => ({
    default: module.PlatformOnboardingPage,
  })),
);
const PlatformEmployeesPage = lazy(() =>
  import("./pages/PlatformGovernancePages").then((module) => ({
    default: module.PlatformEmployeesPage,
  })),
);
const PlatformVisitorsPage = lazy(() =>
  import("./pages/PlatformGovernancePages").then((module) => ({
    default: module.PlatformVisitorsPage,
  })),
);
const PlatformTasksPage = lazy(() =>
  import("./pages/PlatformGovernancePages").then((module) => ({
    default: module.PlatformTasksPage,
  })),
);
const PlatformAuditPage = lazy(() =>
  import("./pages/PlatformGovernancePages").then((module) => ({
    default: module.PlatformAuditPage,
  })),
);
const PlatformHealthPage = lazy(() =>
  import("./pages/PlatformGovernancePages").then((module) => ({
    default: module.PlatformHealthPage,
  })),
);
const MembersPage = lazy(() =>
  import("./pages/MembersPage").then((module) => ({
    default: module.MembersPage,
  })),
);

function toPageProfile(profile: ApiPlatformLlmProfile): PlatformLlmProfile {
  return {
    id: profile.id,
    name: profile.name,
    provider: profile.provider,
    model: profile.model,
    baseUrl: profile.baseUrl,
    keyConfigured: profile.keyConfigured,
    keyHint: profile.keyHint,
    enabled: profile.enabled,
    thinkingMode: profile.thinking,
    reasoningEffort: profile.reasoningEffort,
    timeoutSeconds: profile.timeoutSeconds,
    maxRetries: profile.maxRetries,
    dailyBudgetCny: profile.dailyBudgetCny,
    allowGeneralAnswers: profile.allowGeneralAnswers,
    faqFastPathEnabled: profile.faqFastPathEnabled,
    updatedAt: profile.updatedAt,
    version: profile.version,
  };
}

function llmReadiness(
  profiles: ApiPlatformLlmProfile[],
): PlatformLlmReadiness {
  const active = profiles.find((profile) => profile.isActive);
  if (!active) {
    return {
      status: profiles.length === 0 ? "unconfigured" : "partial",
      message:
        profiles.length === 0
          ? "还没有保存 LLM 配置。"
          : "已有配置，但尚未选择当前主配置。",
      capabilities: [
        { id: "chat_main", label: "名片 AI 问答", status: "unconfigured" },
      ],
    };
  }

  const status = !active.enabled
    ? "disabled"
    : !active.keyConfigured
      ? "unconfigured"
      : active.lastTestStatus === "failed"
        ? "failed"
        : active.lastTestStatus === "untested"
          ? "unconfigured"
          : "ready";
  return {
    status:
      status === "ready" ? "ready" : status === "failed" ? "failed" : "partial",
    message:
      status === "ready"
        ? "当前主配置已通过连接测试，可供名片 AI 问答使用。"
        : status === "failed"
          ? "当前主配置最近一次连接测试失败，请检查后重新测试。"
          : status === "disabled"
            ? "当前主配置已停用，名片 AI 问答暂不可用。"
            : active.keyConfigured
              ? "当前主配置尚未通过连接测试。"
              : "当前主配置尚未写入 API Key。",
    capabilities: [
      {
        id: "chat_main",
        label: "名片 AI 问答",
        status,
        profileName: active.name,
      },
    ],
  };
}

function llmCurrent(
  profiles: ApiPlatformLlmProfile[],
): PlatformLlmCurrentConfig {
  const active = profiles.find((profile) => profile.isActive);
  if (!active) return { source: "unconfigured" };
  return {
    source: "database",
    profileId: active.id,
    profileName: active.name,
    provider: active.provider,
    model: active.model,
    baseUrl: active.baseUrl,
    keyConfigured: active.keyConfigured,
    allowGeneralAnswers: active.allowGeneralAnswers,
    faqFastPathEnabled: active.faqFastPathEnabled,
    updatedAt: active.updatedAt,
  };
}

export function PlatformLlmSettingsRoute() {
  const [profiles, setProfiles] = useState<ApiPlatformLlmProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<ApiError>();

  const refresh = useCallback(async () => {
    setLoading(true);
    setLoadError(undefined);
    try {
      setProfiles(await platformApi.listLlmProfiles());
    } catch (caught) {
      const error =
        caught instanceof ApiError
          ? caught
          : new ApiError("LLM 配置加载失败。", { code: "UNKNOWN_ERROR" });
      setLoadError(error);
      throw error;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh().catch(() => undefined);
  }, [refresh]);

  const pageProfiles = useMemo(() => profiles.map(toPageProfile), [profiles]);
  const current = useMemo(() => llmCurrent(profiles), [profiles]);
  const readiness = useMemo(() => llmReadiness(profiles), [profiles]);

  const save = async (
    input: PlatformLlmProfileInput,
    profile?: PlatformLlmProfile,
  ) => {
    if (profile) {
      const expectedVersion = profile.version;
      if (!expectedVersion) {
        throw new ApiError("配置版本缺失，请刷新后重试。", {
          code: "INVALID_PROFILE_VERSION",
        });
      }
      await platformApi.updateLlmProfile(profile.id, {
        expectedVersion,
        name: input.name,
        provider: input.provider,
        baseUrl: input.baseUrl,
        model: input.model,
        apiKey: input.apiKey || undefined,
        thinking: input.thinkingMode,
        reasoningEffort: input.reasoningEffort,
        timeoutSeconds: input.timeoutSeconds,
        maxRetries: input.maxRetries,
        dailyBudgetCny: input.dailyBudgetCny,
        allowGeneralAnswers: input.allowGeneralAnswers,
        faqFastPathEnabled: input.faqFastPathEnabled,
        enabled: input.enabled,
      });
    } else {
      await platformApi.createLlmProfile({
        name: input.name,
        provider: input.provider,
        baseUrl: input.baseUrl,
        model: input.model,
        apiKey: input.apiKey,
        thinking: input.thinkingMode,
        reasoningEffort: input.reasoningEffort,
        timeoutSeconds: input.timeoutSeconds,
        maxRetries: input.maxRetries,
        dailyBudgetCny: input.dailyBudgetCny,
        allowGeneralAnswers: input.allowGeneralAnswers,
        faqFastPathEnabled: input.faqFastPathEnabled,
        enabled: input.enabled,
      });
    }
    await refresh();
  };

  const test = async (
    input: PlatformLlmProfileInput,
    profile?: PlatformLlmProfile,
  ): Promise<PlatformLlmConnectionResult> => {
    if (!profile) {
      throw new ApiError("请先保存配置，再执行连接测试。", {
        code: "PROFILE_REQUIRED",
      });
    }
    const result = await platformApi.testLlmProfile(
      profile.id,
      input.apiKey || undefined,
    );
    await refresh();
    return {
      ok: result.status === "succeeded",
      provider: result.provider,
      model: result.model,
      latencyMs: result.latencyMs,
      errorCode: result.errorCode,
    };
  };

  const activate = async (profile: PlatformLlmProfile) => {
    const expectedVersion = profile.version;
    if (!expectedVersion) {
      throw new ApiError("配置版本缺失，请刷新后重试。", {
        code: "INVALID_PROFILE_VERSION",
      });
    }
    await platformApi.activateLlmProfile(profile.id, {
      expectedVersion,
      expectedActiveProfileId: profiles.find((value) => value.isActive)?.id,
    });
    await refresh();
  };

  if (loadError && profiles.length === 0) {
    return (
      <main className="page-stack">
        <section className="content-panel">
          <ResourceState
            status="error"
            title="LLM 配置加载失败"
            description={loadError.message}
            errorCode={loadError.code}
            requestId={loadError.requestId}
            onRetry={() => void refresh().catch(() => undefined)}
          />
        </section>
      </main>
    );
  }

  return (
    <PlatformLlmSettingsPage
      profiles={pageProfiles}
      current={current}
      readiness={readiness}
      loading={loading}
      onSave={save}
      onTest={test}
      onActivate={activate}
      onRefresh={() => void refresh().catch(() => undefined)}
    />
  );
}

const LEGACY_ONBOARDING_SESSION_KEY = "cf-platform-onboarding-session";
const ONBOARDING_SESSION_KEY_PREFIX = "cf-platform-onboarding-session";

function onboardingSessionStorageKey(userId?: string): string | undefined {
  return userId
    ? `${ONBOARDING_SESSION_KEY_PREFIX}:${encodeURIComponent(userId)}`
    : undefined;
}

function projectOnboardingAdmin(session: PlatformOnboardingSession) {
  if (!session.adminAccount || !session.adminDisplayName) return undefined;
  return {
    account: session.adminAccount,
    displayName: session.adminDisplayName,
  };
}

function projectOnboardingReview(session: PlatformOnboardingSession) {
  const projection = {
    tenantName: session.tenantName,
    companyName: session.tenantName,
    initialCardDisplayName:
      session.initialCardDisplayName ?? session.adminDisplayName,
    initialCardTitle: session.initialCardTitle,
  };
  return Object.values(projection).some(Boolean) ? projection : undefined;
}

export function PlatformOnboardingRoute() {
  const auth = useAuth();
  const actorId = auth.user?.id;
  const storageKey = useMemo(
    () => onboardingSessionStorageKey(actorId),
    [actorId],
  );
  const [session, setSession] = useState<PlatformOnboardingSession>();
  const [sessionOwnerId, setSessionOwnerId] = useState<string>();
  const [importItems, setImportItems] = useState<PlatformOnboardingImportItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<ApiError>();
  const [importError, setImportError] = useState<ApiError>();
  const [llmAvailability, setLlmAvailability] = useState<
    "ready" | "unavailable" | "failed"
  >("unavailable");
  const [adminSummary, setAdminSummary] = useState<{
    account: string;
    displayName: string;
  }>();
  const [initialReview, setInitialReview] = useState<{
    tenantName?: string;
    companyName?: string;
    initialCardDisplayName?: string;
    initialCardTitle?: string;
  }>();
  const [projectionRevision, setProjectionRevision] = useState(0);
  const ownerIdRef = useRef(actorId);
  const activeSessionIdRef = useRef<string | undefined>(undefined);
  const loadRequestRef = useRef(0);
  ownerIdRef.current = actorId;

  const clearSessionState = useCallback(() => {
    activeSessionIdRef.current = undefined;
    setSession(undefined);
    setSessionOwnerId(undefined);
    setAdminSummary(undefined);
    setInitialReview(undefined);
    setImportItems([]);
    setLoadError(undefined);
    setImportError(undefined);
  }, []);

  const loadSession = useCallback(
    async (sessionId: string) => {
      if (!actorId || !storageKey) return;
      const expectedActorId = actorId;
      const requestId = ++loadRequestRef.current;
      setLoading(true);
      setLoadError(undefined);
      setImportError(undefined);
      try {
        const loaded = await platformApi.getOnboarding(sessionId);
        if (
          ownerIdRef.current !== expectedActorId ||
          loadRequestRef.current !== requestId
        ) {
          return;
        }
        activeSessionIdRef.current = loaded.id;
        setSession(loaded);
        setSessionOwnerId(expectedActorId);
        setAdminSummary(projectOnboardingAdmin(loaded));
        setInitialReview(projectOnboardingReview(loaded));
        setImportItems([]);
        setProjectionRevision((current) => current + 1);
        window.sessionStorage.setItem(storageKey, loaded.id);
      } catch (caught) {
        if (
          ownerIdRef.current !== expectedActorId ||
          loadRequestRef.current !== requestId
        ) {
          return;
        }
        setLoadError(
          caught instanceof ApiError
            ? caught
            : new ApiError("开通会话加载失败。", {
                code: "UNKNOWN_ERROR",
              }),
        );
      } finally {
        if (
          ownerIdRef.current === expectedActorId &&
          loadRequestRef.current === requestId
        ) {
          setLoading(false);
        }
      }
    },
    [actorId, storageKey],
  );

  useEffect(() => {
    ++loadRequestRef.current;
    setLoading(false);
    clearSessionState();
    if (typeof window === "undefined") return;
    window.sessionStorage.removeItem(LEGACY_ONBOARDING_SESSION_KEY);
    if (!actorId || !storageKey) return;
    const stored = window.sessionStorage.getItem(storageKey);
    if (stored) void loadSession(stored);
  }, [actorId, clearSessionState, loadSession, storageKey]);

  const activeSession =
    actorId && sessionOwnerId === actorId ? session : undefined;
  const importBatchKey = activeSession?.importBatchIds.join(":") ?? "";
  useEffect(() => {
    if (
      !actorId ||
      !activeSession ||
      !importBatchKey ||
      ["confirmed", "cancelled", "expired", "failed"].includes(
        activeSession.status,
      )
    ) {
      return;
    }
    const expectedActorId = actorId;
    const expectedSessionId = activeSession.id;
    let cancelled = false;
    let timer: number | undefined;
    const poll = async () => {
      try {
        const status = await platformApi.getOnboardingImports(expectedSessionId);
        if (
          cancelled ||
          ownerIdRef.current !== expectedActorId ||
          activeSessionIdRef.current !== expectedSessionId ||
          status.sessionId !== expectedSessionId
        ) {
          return;
        }
        setImportItems(status.items);
        setImportError(undefined);
        if (!status.settled) timer = window.setTimeout(poll, 1_500);
      } catch (caught) {
        if (
          cancelled ||
          ownerIdRef.current !== expectedActorId ||
          activeSessionIdRef.current !== expectedSessionId
        ) {
          return;
        }
        setImportError(
          caught instanceof ApiError
            ? caught
            : new ApiError("资料解析进度加载失败。", {
                code: "UNKNOWN_ERROR",
              }),
        );
        timer = window.setTimeout(poll, 3_000);
      }
    };
    void poll();
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [activeSession?.id, activeSession?.status, actorId, importBatchKey]);

  useEffect(() => {
    if (!actorId) {
      setLlmAvailability("unavailable");
      return;
    }
    const expectedActorId = actorId;
    let cancelled = false;
    void platformApi
      .listLlmProfiles()
      .then((profiles) => {
        if (cancelled || ownerIdRef.current !== expectedActorId) return;
        const active = profiles.find((profile) => profile.isActive);
        setLlmAvailability(
          active?.enabled &&
            active.keyConfigured &&
            active.lastTestStatus === "succeeded"
            ? "ready"
            : "unavailable",
        );
      })
      .catch(() => {
        if (!cancelled && ownerIdRef.current === expectedActorId) {
          setLlmAvailability("failed");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [actorId]);

  const replaceSession = useCallback(
    (value: PlatformOnboardingSession, expectedSessionId?: string) => {
      if (!actorId || ownerIdRef.current !== actorId || !storageKey) return false;
      if (
        expectedSessionId &&
        activeSessionIdRef.current !== expectedSessionId
      ) {
        return false;
      }
      activeSessionIdRef.current = value.id;
      setSession(value);
      setSessionOwnerId(actorId);
      window.sessionStorage.setItem(storageKey, value.id);
      return true;
    },
    [actorId, storageKey],
  );

  return (
    <PlatformOnboardingPage
      key={`${actorId ?? "anonymous"}:${activeSession?.id ?? "new"}:${projectionRevision}`}
      session={activeSession}
      importItems={activeSession ? importItems : []}
      adminSummary={activeSession ? adminSummary : undefined}
      initialReview={activeSession ? initialReview : undefined}
      llmAvailability={llmAvailability}
      resourceStatus={loading ? "loading" : loadError ? "error" : "ready"}
      resourceError={loadError ?? importError}
      onStart={async (input: StartPlatformOnboardingInput) => {
        const expectedActorId = actorId;
        const created = await platformApi.startOnboarding(input);
        if (!expectedActorId || ownerIdRef.current !== expectedActorId) return;
        setAdminSummary({
          account: input.adminAccount,
          displayName: input.adminDisplayName,
        });
        setInitialReview({
          tenantName: input.tenantName,
          companyName: input.tenantName,
          initialCardDisplayName: input.adminDisplayName,
        });
        setImportItems([]);
        setImportError(undefined);
        replaceSession(created);
      }}
      onUpload={async (sessionId: string, files: File[]) => {
        const updated = await platformApi.uploadOnboardingDocuments(sessionId, files);
        if (!replaceSession(updated, sessionId)) return;
        setImportItems([]);
        setImportError(undefined);
      }}
      onGenerate={async (sessionId: string, expectedVersion: number) => {
        const updated = await platformApi.generateOnboardingSuggestions(
          sessionId,
          expectedVersion,
        );
        replaceSession(updated, sessionId);
      }}
      onConfirm={async (
        sessionId: string,
        input: ConfirmPlatformOnboardingInput,
      ) => {
        const updated = await confirmOnboardingWithRecovery({
          confirm: () => platformApi.confirmOnboarding(sessionId, input),
          reload: () => platformApi.getOnboarding(sessionId),
        });
        replaceSession(updated, sessionId);
        return updated;
      }}
      onCancel={async (
        sessionId: string,
        reason: string,
        expectedVersion: number,
      ) => {
        const updated = await platformApi.cancelOnboarding(
          sessionId,
          reason,
          expectedVersion,
        );
        replaceSession(updated, sessionId);
      }}
      onRefresh={() => {
        if (activeSession?.id) void loadSession(activeSession.id);
      }}
      onStartAnother={() => {
        ++loadRequestRef.current;
        if (storageKey) window.sessionStorage.removeItem(storageKey);
        clearSessionState();
      }}
      onOpenEnterprises={() => navigate(APP_PATHS.platformEnterprises)}
    />
  );
}

function RouteRedirect({ path }: { path: AppPath }) {
  useEffect(() => navigate(path), [path]);
  return (
    <main className="page-stack">
      <section className="content-panel">
        <ResourceState status="loading" />
      </section>
    </main>
  );
}

function WorkspaceForbidden({ destination }: { destination: AppPath }) {
  return (
    <main className="page-stack">
      <section className="content-panel">
        <ResourceState
          status="permission"
          title="无法访问此工作区"
          description="当前账号与该控制台不匹配（403）。请返回当前账号所属工作区。"
        />
        <Button appearance="primary" onClick={() => navigate(destination)}>
          返回当前工作区
        </Button>
      </section>
    </main>
  );
}

export function CurrentPage() {
  const pathname = usePathname();
  const auth = useAuth();
  const userWorkspace = adminWorkspaceForUser(auth.user);
  if (pathname === APP_PATHS.overview && userWorkspace === "platform") {
    return <RouteRedirect path={APP_PATHS.platformOverview} />;
  }
  const routeWorkspace = adminWorkspaceForPath(pathname);
  if (
    routeWorkspace &&
    !canAccessAdminWorkspace(auth.user, routeWorkspace) &&
    userWorkspace
  ) {
    return (
      <WorkspaceForbidden
        destination={
          userWorkspace === "platform"
            ? APP_PATHS.platformOverview
            : APP_PATHS.overview
        }
      />
    );
  }
  if (pathname === APP_PATHS.platformOverview) return <PlatformOverviewPage />;
  if (pathname === APP_PATHS.platformLlmSettings) {
    return <PlatformLlmSettingsRoute />;
  }
  if (pathname === APP_PATHS.platformOnboarding) {
    return <PlatformOnboardingRoute />;
  }
  if (pathname === APP_PATHS.platformEmployees) return <PlatformEmployeesPage />;
  if (pathname === APP_PATHS.platformVisitors) return <PlatformVisitorsPage />;
  if (pathname === APP_PATHS.platformTasks) return <PlatformTasksPage />;
  if (pathname === APP_PATHS.platformAudit) return <PlatformAuditPage />;
  if (pathname === APP_PATHS.platformHealth) return <PlatformHealthPage />;
  if (pathname === APP_PATHS.visits) return <VisitsPage />;
  if (pathname === APP_PATHS.visitorProfiles) return <VisitorProfilesPage />;
  if (pathname === APP_PATHS.conversations) return <ConversationsPage />;
  if (pathname === APP_PATHS.opportunities) return <OpportunitiesPage />;
  if (pathname === APP_PATHS.leads) return <LeadsPage />;
  if (pathname === APP_PATHS.exports) return <ExportsPage />;
  if (pathname === APP_PATHS.knowledgeGaps) return <KnowledgeGapsPage />;
  if (pathname === APP_PATHS.notifications) return <NotificationsPage />;
  if (pathname === APP_PATHS.privacyRequests) return <PrivacyRequestsPage />;
  if (pathname === APP_PATHS.setup) return <CompanySetupPage />;
  if (pathname === APP_PATHS.company) return <CompanyProfilePage />;
  if (pathname === APP_PATHS.members) return <MembersPage />;
  if (pathname === APP_PATHS.card) return <CardSettingsPage />;
  if (pathname === APP_PATHS.cards) return <CardsPage />;
  if (pathname === APP_PATHS.products) return <ProductsPage />;
  if (pathname === APP_PATHS.cases) return <CaseStudiesPage />;
  if (pathname === APP_PATHS.forbiddenTopics) return <ForbiddenTopicsPage />;
  if (pathname === APP_PATHS.knowledge) return <KnowledgePage />;
  if (pathname === APP_PATHS.platformEnterprises) return <PlatformEnterprisesPage />;
  if (pathname === APP_PATHS.overview) {
    return <OverviewPage />;
  }

  return (
    <main className="page-stack">
      <section className="content-panel">
        <ResourceState
          status="empty"
          title="页面不存在"
          description="当前地址不属于企业管理工作台。"
          emptyAction={
            <Button appearance="primary" onClick={() => navigate(APP_PATHS.overview)}>
              返回概览
            </Button>
          }
        />
      </section>
    </main>
  );
}

function AuthenticatedApplication() {
  return (
    <AppShell>
      <Suspense
        fallback={
          <main className="page-stack">
            <section className="content-panel">
              <ResourceState status="loading" />
            </section>
          </main>
        }
      >
        <CurrentPage />
      </Suspense>
    </AppShell>
  );
}

export function SessionGate() {
  const auth = useAuth();
  const pathname = usePathname();
  const workspace = adminWorkspaceForUser(auth.user);
  const landingPath =
    workspace === "platform" ? APP_PATHS.platformOverview : APP_PATHS.overview;
  const authenticationLandingPath =
    pathname === WECOM_ENTRY_PATH && workspace === "enterprise"
      ? APP_PATHS.setup
      : landingPath;
  const isAuthenticationEntry =
    pathname === "/login" || pathname === WECOM_ENTRY_PATH;

  useEffect(() => {
    if (auth.status === "authenticated" && isAuthenticationEntry && workspace) {
      navigate(authenticationLandingPath);
    }
  }, [auth.status, authenticationLandingPath, isAuthenticationEntry, workspace]);

  if (auth.status === "bootstrapping") return <BootScreen />;
  if (auth.status === "unauthenticated") return <LoginPage />;
  if (isAuthenticationEntry && workspace) return <BootScreen />;
  return <AuthenticatedApplication />;
}

export function App() {
  return (
    <AuthProvider>
      <SessionGate />
    </AuthProvider>
  );
}
