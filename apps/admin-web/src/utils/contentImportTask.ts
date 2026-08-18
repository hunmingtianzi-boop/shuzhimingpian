export const CONTENT_IMPORT_TASK_EVENT = "content-import-task-changed";
const STORAGE_KEY = "cf-content-import-active-task";

export type RememberedContentImportTask = {
  runId: string;
  batchId: string;
};

export function rememberContentImportTask(runId: string, batchId: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ runId, batchId }));
  window.dispatchEvent(new Event(CONTENT_IMPORT_TASK_EVENT));
}

export function readRememberedContentImportTask(): RememberedContentImportTask | undefined {
  if (typeof window === "undefined") return undefined;
  try {
    const value = JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? "null") as unknown;
    if (
      typeof value === "object" && value !== null
      && "runId" in value && typeof value.runId === "string"
      && "batchId" in value && typeof value.batchId === "string"
    ) {
      return { runId: value.runId, batchId: value.batchId };
    }
  } catch {
    // A malformed local hint is disposable; the API remains authoritative.
  }
  return undefined;
}

export function clearRememberedContentImportTask(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(STORAGE_KEY);
}
