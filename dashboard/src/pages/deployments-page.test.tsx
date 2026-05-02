import userEvent from "@testing-library/user-event";
import { screen, waitFor, within } from "@testing-library/react";

import { writeToken } from "@/lib/auth-storage";
import { installMockFetch, ok } from "@/test/mock-api";
import { renderApp } from "@/test/render-app";

describe("deployments page", () => {
  it("renders deployments and creates an image-backed deployment from custom images", async () => {
    writeToken("header.payload.signature");
    const deployments = [
      {
        name: "Fraud Prod",
        slug: "fraud-prod",
        status: "ACTIVE",
        endpoint_url: "http://gateway.mldlc.local/api/v1/deployments/fraud-prod:predict",
        input_schema: { type: "object", properties: { amount: { type: "number" } } },
        output_schema: { type: "object", properties: { score: { type: "number" } } },
        created_at: "2026-04-01T10:00:00Z",
        labels: { env: "prod" },
        source_type: "image",
        image_ref: "gitea.mldlc.local/user/fraud:latest",
      },
    ];

    const fetchMock = installMockFetch([
      { method: "GET", path: "/users/me", handler: () => ok({ email: "user@example.com", is_active: true, is_superuser: false, is_verified: true, created_at: "2026-04-01T10:00:00Z" }) },
      { method: "GET", path: "/deployments", handler: () => ok(deployments) },
      { method: "GET", path: "/repositories", handler: () => ok([]) },
      {
        method: "GET",
        path: "/artifact-registry/status",
        handler: () => ok({
          enabled: true,
          registry_host: "gitea.mldlc.local",
          username: "user",
          namespace: "gitea.mldlc.local/user",
          docker_login_command: "docker login gitea.mldlc.local -u user --password-stdin",
        }),
      },
      { method: "GET", path: "/artifact-registry/tokens", handler: () => ok([]) },
      {
        method: "GET",
        path: "/artifact-registry/images",
        handler: () => ok([
          {
            name: "fraud",
            tags: [
              {
                tag: "latest",
                image_ref: "gitea.mldlc.local/user/fraud:latest",
                created_at: "2026-04-01T10:00:00Z",
              },
            ],
          },
        ]),
      },
      {
        method: "POST",
        path: "/artifact-registry/images/fraud/tags/latest/deployments",
        handler: async (request) => {
          const body = await request.json() as { name: string };
          const created = {
            ...deployments[0],
            name: body.name,
            slug: "fraud-canary",
            status: "PENDING",
          };
          deployments.unshift(created);
          return ok(created, 201);
        },
      },
      {
        method: "GET",
        path: "/deployments/fraud-canary",
        handler: () => ok({
          ...deployments[0],
          name: "Fraud Canary",
          slug: "fraud-canary",
          status: "PENDING",
        }),
      },
      { method: "GET", path: "/deployments/fraud-canary/dashboards", handler: () => ok([]) },
      { method: "GET", path: "/deployments/fraud-canary/plot-fields", handler: () => ok([]) },
    ]);

    renderApp("/deployments");

    expect(await screen.findByText("Model serving")).toBeInTheDocument();
    expect(await screen.findByText("Fraud Prod")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Create deployment" }));
    await userEvent.click(await screen.findByRole("button", { name: /Custom image/i }));
    expect(await screen.findByText("gitea.mldlc.local/user/fraud:latest")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /latest/i }));

    const configPanel = screen.getByText("Configuration").closest("section");
    expect(configPanel).not.toBeNull();
    await userEvent.type(within(configPanel as HTMLElement).getByPlaceholderText("fraud prod"), "Fraud Canary");
    await userEvent.click(within(configPanel as HTMLElement).getByRole("button", { name: "Deploy" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/artifact-registry/images/fraud/tags/latest/deployments"),
        expect.objectContaining({ method: "POST" }),
      );
    });
  });
});
