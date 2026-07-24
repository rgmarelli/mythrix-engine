import '@testing-library/jest-dom/vitest';

// jsdom does not implement scrollIntoView; components call it purely as a
// side effect (HotspotDetailPanel's chip-to-segment navigation).
Element.prototype.scrollIntoView = Element.prototype.scrollIntoView ?? (() => {});
