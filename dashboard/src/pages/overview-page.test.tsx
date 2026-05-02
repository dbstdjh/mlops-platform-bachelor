import { screen } from "@testing-library/react";

import { writeToken } from "@/lib/auth-storage";
import { renderApp } from "@/test/render-app";
import { installMockFetch, ok } from "@/test/mock-api";

function bootstrapRoutes(overrides?: Partial<Record<string, unknown>>) {
  return [
    { method: "GET", path: "/users/me", handler: () => ok(overrides?.me ?? { email: "user@example.com", is_active: true, is_superuser: false, is_verified: true, created_at: "2026-04-01T10:00:00Z" }) },
    { method: "GET", path: "/overview/summary", handler: () => ok(overrides?.summary ?? { experiment_count: 0, dataset_count: 0, repository_count: 0, deployment_count: 0 }) },
    { method: "GET", path: "/overview/recent", handler: () => ok(overrides?.recent ?? { experiments: [], datasets: [], repositories: [], deployments: [] }) },
  ];
}

describe("overview page", () => {
  it("shows loading and then empty states", async () => {
    writeToken("header.payload.signature");
    installMockFetch(bootstrapRoutes());

    renderApp("/overview");

    expect(screen.getByText("Bootstrapping session")).toBeInTheDocument();
    expect(await screen.findByText("No experiments yet")).toBeInTheDocument();
    expect(screen.getByText("No datasets uploaded yet.")).toBeInTheDocument();
  });

  it("renders an error state when overview fetching fails", async () => {
    writeToken("header.payload.signature");
    installMockFetch([
      { method: "GET", path: "/users/me", handler: () => ok({ email: "user@example.com", is_active: true, is_superuser: false, is_verified: true, created_at: "2026-04-01T10:00:00Z" }) },
      { method: "GET", path: "/overview/summary", handler: () => ({ status: 500, body: { detail: "Boom" } }) },
      { method: "GET", path: "/overview/recent", handler: () => ok({ experiments: [], datasets: [], repositories: [], deployments: [] }) },
    ]);

    renderApp("/overview");

    expect(
      await screen.findByText("The dashboard could not load overview data from the control plane.", {}, { timeout: 3000 }),
    ).toBeInTheDocument();
  });
});
