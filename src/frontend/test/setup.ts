import "@testing-library/jest-dom";

// En Node 22/24 con jsdom, undici verifica signal contra el AbortSignal interno de Node,
// el cual difiere del AbortSignal del realm de jsdom. Para evitar TypeError en createClientSideRequest
// de React Router y en fetch() de TanStack Query durante los tests, adaptamos Request y fetch.
const OriginalRequest = globalThis.Request;
// @ts-expect-error polyfill realm undici+jsdom
globalThis.Request = class Request extends OriginalRequest {
  constructor(input: RequestInfo | URL, init?: RequestInit) {
    if (init && "signal" in init) {
      const { signal: _, ...resto } = init;
      super(input, resto);
      return;
    }
    super(input, init);
  }
};

const OriginalFetch = globalThis.fetch;
globalThis.fetch = function (input: RequestInfo | URL, init?: RequestInit) {
  if (init && "signal" in init) {
    const { signal: _, ...resto } = init;
    return OriginalFetch(input, resto);
  }
  return OriginalFetch(input, init);
};
