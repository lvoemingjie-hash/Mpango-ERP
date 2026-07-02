import '@testing-library/jest-dom';

// Polyfill ResizeObserver for jsdom (required by @headlessui/react Dialog)
class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver = ResizeObserverMock as unknown as typeof ResizeObserver;
