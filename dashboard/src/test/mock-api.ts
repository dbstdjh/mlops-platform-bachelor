import { vi } from "vitest";

type MockBody = Record<string, unknown> | unknown[] | string | null;
type Handler = (request: Request) => Promise<{ status?: number; body?: MockBody }> | { status?: number; body?: MockBody };

export interface MockRoute {
  method: string;
  path: string;
  handler: Handler;
}

function jsonResponse(body: MockBody, status = 200): Response {
  return new Response(body == null ? null : JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json",
    },
  });
}

export function installMockFetch(routes: MockRoute[]) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const request = new Request(input, init);
    const url = new URL(request.url);
    const pathname = url.pathname.replace(/^.*\/api\/v1/, "");
    const match = routes.find((route) => route.method === request.method && route.path === pathname);

    if (!match) {
      return jsonResponse({ detail: `No mock for ${request.method} ${pathname}` }, 500);
    }

    const result = await match.handler(request);
    return jsonResponse(result.body ?? null, result.status ?? 200);
  });

  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

export function ok(body: MockBody, status = 200) {
  return { status, body };
}
