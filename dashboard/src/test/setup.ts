import "@testing-library/jest-dom/vitest";

import { afterEach, beforeAll, vi } from "vitest";
import { cleanup } from "@testing-library/react";

class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}

beforeAll(() => {
  vi.stubGlobal("ResizeObserver", ResizeObserverMock);
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  );
  vi.stubGlobal("scrollTo", vi.fn());
  vi.spyOn(window, "open").mockImplementation(() => null);
  Object.defineProperty(HTMLElement.prototype, "clientWidth", {
    configurable: true,
    value: 1024,
  });
  Object.defineProperty(HTMLElement.prototype, "clientHeight", {
    configurable: true,
    value: 768,
  });
  Object.defineProperty(HTMLElement.prototype, "offsetWidth", {
    configurable: true,
    value: 1024,
  });
  Object.defineProperty(HTMLElement.prototype, "offsetHeight", {
    configurable: true,
    value: 768,
  });
  HTMLElement.prototype.getBoundingClientRect = () =>
    ({
      width: 1024,
      height: 768,
      top: 0,
      left: 0,
      bottom: 768,
      right: 1024,
      x: 0,
      y: 0,
      toJSON() {
        return {};
      },
    }) as DOMRect;
});

afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.restoreAllMocks();
});
