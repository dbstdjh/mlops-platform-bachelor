import { clearToken, isTokenExpired, parseJwtPayload, readToken, writeToken } from "@/lib/auth-storage";

function makeToken(payload: Record<string, unknown>) {
  const body = btoa(JSON.stringify(payload)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  return `header.${body}.signature`;
}

describe("auth storage", () => {
  it("writes and reads tokens from localStorage", () => {
    writeToken("test-token");

    expect(readToken()).toBe("test-token");

    clearToken();

    expect(readToken()).toBeNull();
  });

  it("parses JWT payloads and detects expiration", () => {
    const freshToken = makeToken({ exp: Math.floor(Date.now() / 1000) + 120 });
    const expiredToken = makeToken({ exp: Math.floor(Date.now() / 1000) - 120 });

    expect(parseJwtPayload(freshToken)).toMatchObject({ exp: expect.any(Number) });
    expect(isTokenExpired(freshToken)).toBe(false);
    expect(isTokenExpired(expiredToken)).toBe(true);
  });
});
