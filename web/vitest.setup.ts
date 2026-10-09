import "@testing-library/jest-dom/vitest";

// Node 22+ ships an experimental global `localStorage`/`sessionStorage` that shadows jsdom's
// and is unusable without --localstorage-file (no clear/getItem). Swap in an in-memory Storage.
for (const name of ["localStorage", "sessionStorage"] as const) {
  if (typeof globalThis[name]?.clear === "function") continue;
  const data = new Map<string, string>();
  const shim: Storage = {
    get length() { return data.size; },
    clear: () => data.clear(),
    getItem: (k) => (data.has(k) ? data.get(k)! : null),
    key: (i) => Array.from(data.keys())[i] ?? null,
    removeItem: (k) => { data.delete(k); },
    setItem: (k, v) => { data.set(k, String(v)); },
  };
  Object.defineProperty(globalThis, name, { value: shim, configurable: true, writable: true });
}
