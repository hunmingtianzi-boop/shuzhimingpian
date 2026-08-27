export const PLATFORM_ONBOARDING_TASK_EVENT = "platform-onboarding-task-changed";
const STORAGE_KEY = "cf-platform-onboarding-active-analysis";

export type RememberedPlatformOnboardingTask = {
  sessionId: string;
  displayName: string;
  startedAt: string;
};

export function rememberPlatformOnboardingTask(sessionId: string, displayName: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify({
    sessionId,
    displayName,
    startedAt: new Date().toISOString(),
  }));
  window.dispatchEvent(new Event(PLATFORM_ONBOARDING_TASK_EVENT));
}

export function notifyPlatformOnboardingTaskChanged(): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new Event(PLATFORM_ONBOARDING_TASK_EVENT));
}

export function readRememberedPlatformOnboardingTask(): RememberedPlatformOnboardingTask | undefined {
  if (typeof window === "undefined") return undefined;
  try {
    const value = JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? "null") as unknown;
    if (
      typeof value === "object" && value !== null
      && "sessionId" in value && typeof value.sessionId === "string"
      && "displayName" in value && typeof value.displayName === "string"
      && "startedAt" in value && typeof value.startedAt === "string"
    ) {
      return value as RememberedPlatformOnboardingTask;
    }
  } catch {
    // The server remains authoritative; malformed local navigation hints are disposable.
  }
  return undefined;
}

export function clearRememberedPlatformOnboardingTask(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(STORAGE_KEY);
}
