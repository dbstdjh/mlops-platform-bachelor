import { screen } from "@testing-library/react";

import { writeToken } from "@/lib/auth-storage";
import { renderApp } from "@/test/render-app";
import { installMockFetch, ok } from "@/test/mock-api";

describe("experiment detail page", () => {
  it("renders experiment metadata and run links without experiment-wide plots", async () => {
    writeToken("header.payload.signature");
    installMockFetch([
      { method: "GET", path: "/users/me", handler: () => ok({ email: "user@example.com", is_active: true, is_superuser: false, is_verified: true, created_at: "2026-04-01T10:00:00Z" }) },
      { method: "GET", path: "/experiments/iris-exp", handler: () => ok({ name: "Iris experiment", slug: "iris-exp", logged_data_template: ["loss", "accuracy"], created_at: "2026-04-01T10:00:00Z", labels: { stage: "baseline" }, run_count: 2, latest_run: null }) },
      {
        method: "GET",
        path: "/experiments/iris-exp/runs",
        handler: () =>
          ok([
            {
              experiment_slug: "iris-exp",
              run_number: 1,
              status: "COMPLETED",
              created_at: "2026-04-01T10:00:00Z",
              ended_at: "2026-04-01T10:10:00Z",
              dataset: null,
              model: null,
              latest_metrics: { loss: 0.12, accuracy: 0.98, precision: 0.95, recall: 0.94, f1: 0.945, auc: 0.99 },
              labels: {},
            },
          ]),
      },
    ]);

    renderApp("/experiments/iris-exp");

    expect(await screen.findByText("Iris experiment")).toBeInTheDocument();
    expect(screen.queryByText("Compare selected runs")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open run" })).toBeInTheDocument();
    expect(screen.getByText("stage:baseline")).toBeInTheDocument();
    expect(screen.getByText("+2 more")).toBeInTheDocument();
    expect(screen.getByText("auc")).toBeInTheDocument();
  });
});
