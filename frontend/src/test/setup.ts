// Global test setup.
//
// Unmount between tests so a component's effects (and any timers or object URLs
// they hold) do not leak into the next one. Without this, React Testing Library
// keeps every render mounted in the same jsdom document and queries start
// matching elements from a previous test.
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(() => {
  cleanup();
});

// jsdom implements neither of these, and PdfPreview calls both: it creates an
// object URL for the blob and revokes it on unmount. Stubbing them here keeps
// the component under test honest (it still calls them) without every spec
// having to know that.
if (typeof URL.createObjectURL === "undefined") {
  URL.createObjectURL = () => "blob:mock";
  URL.revokeObjectURL = () => {};
}
