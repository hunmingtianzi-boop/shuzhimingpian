export function resolvePublicResourceUrl(value?: string | null): string | undefined {
  const resource = value?.trim();
  if (!resource) return undefined;
  if (!resource.startsWith("/api/")) return resource;

  const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? "").trim();
  if (!apiBaseUrl) return resource;

  try {
    const base = new URL(apiBaseUrl, globalThis.location?.origin ?? "http://localhost");
    const apiMarkerIndex = base.pathname.indexOf("/api/");
    const deploymentPrefix = apiMarkerIndex >= 0
      ? base.pathname.slice(0, apiMarkerIndex)
      : "";
    return new URL(`${deploymentPrefix}${resource}`, base.origin).toString();
  } catch {
    return resource;
  }
}
