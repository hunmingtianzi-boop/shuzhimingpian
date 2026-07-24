import "@testing-library/jest-dom/vitest";
import { cleanup, configure } from "@testing-library/react";
import { disposeTabster, getTabster } from "tabster";
import { afterEach } from "vitest";

// GitHub's shared runners can take over one second to commit jsdom updates
// while other CI jobs are active. Keep async assertions bounded, but allow
// enough time for real resource and Fluent portal state to settle.
configure({ asyncUtilTimeout: 5_000 });

afterEach(() => {
  cleanup();
  const tabster = getTabster(window);
  if (tabster) {
    disposeTabster(tabster, true);
  }
  document.body.replaceChildren();
  document.body.removeAttribute("aria-hidden");
  document.body.removeAttribute("data-tabster");
});

class ResizeObserverStub implements ResizeObserver {
  disconnect() {}
  observe() {}
  unobserve() {}
}

if (!globalThis.ResizeObserver) {
  globalThis.ResizeObserver = ResizeObserverStub;
}

Object.defineProperty(globalThis, "matchMedia", {
  configurable: true,
  value: (query: string): MediaQueryList => ({
    // Animations are not observable product behavior in unit tests. Enabling
    // reduced motion prevents Fluent's exiting modalizer from overlapping the
    // next dialog and asynchronously changing its aria-hidden state.
    matches: query.includes("prefers-reduced-motion: reduce"),
    media: query,
    onchange: null,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    addListener: () => undefined,
    removeListener: () => undefined,
    dispatchEvent: () => false,
  }),
});
