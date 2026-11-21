import "@testing-library/jest-dom/vitest";
class RO { observe() {} unobserve() {} disconnect() {} }
(globalThis as unknown as { ResizeObserver: typeof RO }).ResizeObserver = RO;

// jsdom lacks layout APIs that real browsers provide
Element.prototype.scrollIntoView = () => {};
