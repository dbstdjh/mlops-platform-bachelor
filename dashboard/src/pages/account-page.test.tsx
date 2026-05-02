import userEvent from "@testing-library/user-event";
import { screen } from "@testing-library/react";

import { writeToken } from "@/lib/auth-storage";
import { renderApp } from "@/test/render-app";
import { installMockFetch, ok } from "@/test/mock-api";

describe("account page", () => {
  it("creates and revokes API keys while only showing the secret once", async () => {
    writeToken("header.payload.signature");
    const keys = [
      {
        name: "existing",
        prefix: "mlp_existing",
        is_revoked: false,
        created_at: "2026-04-01T10:00:00Z",
      },
    ];

    installMockFetch([
      { method: "GET", path: "/users/me", handler: () => ok({ email: "user@example.com", is_active: true, is_superuser: false, is_verified: true, created_at: "2026-04-01T10:00:00Z" }) },
      { method: "GET", path: "/users/me/api-keys", handler: () => ok(keys) },
      {
        method: "GET",
        path: "/artifact-registry/status",
        handler: () => ok({
          enabled: true,
          registry_host: "gitea.mldlc.local",
          username: "mldlc-user",
          namespace: "gitea.mldlc.local/mldlc-user",
          docker_login_command: "docker login gitea.mldlc.local -u mldlc-user --password-stdin",
        }),
      },
      { method: "GET", path: "/artifact-registry/tokens", handler: () => ok([]) },
      { method: "GET", path: "/artifact-registry/images", handler: () => ok([{ name: "fraud", tags: [{ tag: "latest", image_ref: "gitea.mldlc.local/mldlc-user/fraud:latest", created_at: null }] }]) },
      {
        method: "POST",
        path: "/users/me/api-keys",
        handler: async () => {
          const created = {
            name: "sdk",
            prefix: "mlp_sdk",
            is_revoked: false,
            created_at: "2026-04-02T10:00:00Z",
            api_key: "mlp_secret_123",
          };
          keys.unshift({ ...created, api_key: undefined } as never);
          return ok(created, 201);
        },
      },
      {
        method: "POST",
        path: "/users/me/api-keys/existing:revoke",
        handler: () => {
          keys[0].is_revoked = true;
          return ok({ status: "ok" });
        },
      },
    ]);

    renderApp("/account");

    expect(await screen.findByText("Profile and API keys")).toBeInTheDocument();
    await userEvent.type(screen.getByPlaceholderText("sdk"), "sdk");
    await userEvent.click(screen.getByRole("button", { name: "Create API key" }));

    expect(await screen.findByText("mlp_secret_123")).toBeInTheDocument();
    await userEvent.click(screen.getAllByRole("button", { name: "Revoke" })[0]);
  });
});
