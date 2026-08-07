import { afterEach, describe, expect, it, vi } from "vitest";

import { resolvePublicResourceUrl } from "./publicResourceUrl";

describe("resolvePublicResourceUrl", () => {
  afterEach(() => vi.unstubAllEnvs());

  it("uses the API origin for stored relative asset paths", () => {
    vi.stubEnv("VITE_API_BASE_URL", "https://api.example.test/api/v1");

    expect(resolvePublicResourceUrl("/api/v1/public/card-assets/company/image.webp")).toBe(
      "https://api.example.test/api/v1/public/card-assets/company/image.webp",
    );
  });

  it("does not rewrite tenant assets or external URLs", () => {
    vi.stubEnv("VITE_API_BASE_URL", "https://api.example.test/api/v1");

    expect(resolvePublicResourceUrl("/tenants/example/logo.svg")).toBe("/tenants/example/logo.svg");
    expect(resolvePublicResourceUrl("https://cdn.example.test/image.webp")).toBe(
      "https://cdn.example.test/image.webp",
    );
  });
});
