(function bootstrapPublicCardRequest() {
  if (new URLSearchParams(window.location.search).has("mock-card")) return;
  var match = window.location.pathname.match(/(?:^|\/)c\/([^/?#]+)\/?$/i);
  if (!match) return;

  var slug;
  try {
    slug = decodeURIComponent(match[1]).trim().toLowerCase();
  } catch (_error) {
    return;
  }
  if (!/^[a-z0-9][a-z0-9-]{1,94}[a-z0-9]$/.test(slug)) return;

  var script = document.currentScript;
  if (!script || !script.src) return;
  var apiBaseMeta = document.querySelector('meta[name="cf-api-base"]');
  var configuredBase = apiBaseMeta
    ? (apiBaseMeta.getAttribute("content") || "").trim()
    : "";
  var apiBase = configuredBase && configuredBase.charAt(0) !== "%"
    ? new URL(configuredBase.replace(/\/+$/, "") + "/", window.location.origin)
    : new URL("api/v1/", new URL(".", script.src));
  var endpoint = new URL(
    "public/cards/" + encodeURIComponent(slug),
    apiBase,
  ).href;

  var promise = fetch(endpoint, {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  }).then(function readPublicCardResponse(response) {
    return response.json().then(function keepResponseMetadata(payload) {
      return {
        ok: response.ok,
        payload: payload,
        status: response.status,
      };
    });
  });
  // Attach a handler immediately so an early network failure is not reported
  // as unhandled before the React bootstrap adopts this same promise.
  promise.catch(function ignoreUntilApplicationBootstrap() {});

  window.__CF_PUBLIC_CARD_BOOTSTRAP__ = {
    endpoint: endpoint,
    slug: slug,
    promise: promise,
  };
})();
