import { api, ApiError, setUnauthorizedHandler } from "@/lib/api";
import { writeToken } from "@/lib/auth-storage";

describe("api client", () => {
  it("maps error payloads into ApiError and triggers unauthorized handler", async () => {
    const onUnauthorized = vi.fn();
    setUnauthorizedHandler(onUnauthorized);
    writeToken("header.payload.signature");

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "Invalid credentials" }), {
          status: 401,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(api.listDatasets()).rejects.toMatchObject<ApiError>({
      status: 401,
      detail: "Invalid credentials",
    });
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
  });

  it("sends JSON bodies for public auth endpoints", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ access_token: "jwt-token", token_type: "bearer" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await api.login({ email: "user@example.com", password: "Secret123" });

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/users:login"),
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ email: "user@example.com", password: "Secret123" }),
      }),
    );
  });
});
