import { screen } from "@testing-library/react";

import { writeToken } from "@/lib/auth-storage";
import { renderApp } from "@/test/render-app";
import { installMockFetch, ok } from "@/test/mock-api";

function bootstrapRoutes(overrides?: Partial<Record<string, unknown>>) {
  return [
    { method: "GET", path: "/users/me", handler: () => ok(overrides?.me ?? { email: "user@example.com", is_active: true, is_superuser: false, is_verified: true, created_at: "2026-04-01T10:00:00Z" }) },
    { method: "GET", path: "/experiments", handler: () => ok(overrides?.experiments ?? []) },
    { method: "GET", path: "/datasets", handler: () => ok(overrides?.datasets ?? []) },
    { method: "GET", path: "/repositories", handler: () => ok(overrides?.repositories ?? []) },
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
      { method: "GET", path: "/experiments", handler: () => ({ status: 500, body: { detail: "Boom" } }) },
      { method: "GET", path: "/datasets", handler: () => ok([]) },
      { method: "GET", path: "/repositories", handler: () => ok([]) },
    ]);

    renderApp("/overview");

    expect(
      await screen.findByText("The dashboard could not load overview data from the control plane.", {}, { timeout: 3000 }),
    ).toBeInTheDocument();
  });
});
