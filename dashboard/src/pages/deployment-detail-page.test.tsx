import userEvent from "@testing-library/user-event";
import { screen, waitFor, within } from "@testing-library/react";
import { vi } from "vitest";

import { writeToken } from "@/lib/auth-storage";
import { installMockFetch, ok } from "@/test/mock-api";
import { renderApp } from "@/test/render-app";

describe("deployment detail page", () => {
  it("renders default observability panels in a grid and creates a custom plot", async () => {
    writeToken("header.payload.signature");
    const dashboards = [
      {
        id: "latency",
        title: "Latency",
        plot_type: "latency",
        source: "system",
        field_path: "latency_ms",
        is_system_locked: true,
        iframe_url: "http://grafana.local/d-solo/latency",
        created_at: "2026-04-01T10:00:00Z",
      },
      {
        id: "status",
        title: "Status codes",
        plot_type: "status_code",
        source: "system",
        field_path: "status_code",
        is_system_locked: true,
        iframe_url: "http://grafana.local/d-solo/status",
        created_at: "2026-04-01T10:00:00Z",
      },
    ];

    installMockFetch([
      { method: "GET", path: "/users/me", handler: () => ok({ email: "user@example.com", is_active: true, is_superuser: false, is_verified: true, created_at: "2026-04-01T10:00:00Z" }) },
      {
        method: "GET",
        path: "/deployments/fraud-prod",
        handler: () => ok({
          name: "Fraud Prod",
          slug: "fraud-prod",
          status: "ACTIVE",
          endpoint_url: "http://gateway.mldlc.local/api/v1/deployments/fraud-prod:predict",
          input_schema: {
            type: "object",
            properties: {
              instances: {
                type: "array",
                items: { type: "array", minItems: 3, maxItems: 3, items: { type: "number" } },
              },
            },
          },
          output_schema: {
            type: "object",
            properties: {
              predictions: { type: "array", items: { type: "string" } },
              scores: { type: "array", items: { type: "number" } },
            },
          },
          created_at: "2026-04-01T10:00:00Z",
          labels: { env: "prod" },
          source_type: "image",
          image_ref: "gitea.mldlc.local/user/fraud:latest",
        }),
      },
      { method: "GET", path: "/deployments/fraud-prod/dashboards", handler: () => ok(dashboards) },
      {
        method: "GET",
        path: "/deployments/fraud-prod/plot-fields",
        handler: () => ok([
          { source: "input", path: "instances[*][*]", value_type: "number_matrix", plot_types: ["distribution"] },
          { source: "input", path: "instances[*][0]", value_type: "number_matrix_index", plot_types: ["time_series", "distribution"] },
          { source: "input", path: "instances[*][1]", value_type: "number_matrix_index", plot_types: ["time_series", "distribution"] },
          { source: "input", path: "instances[*][2]", value_type: "number_matrix_index", plot_types: ["time_series", "distribution"] },
          { source: "output", path: "predictions[*]", value_type: "category_array", plot_types: ["distribution", "category_time_series"] },
          { source: "output", path: "scores[*]", value_type: "number_array", plot_types: ["time_series", "distribution"] },
        ]),
      },
      {
        method: "POST",
        path: "/deployments/fraud-prod/dashboards",
        handler: async (request) => {
          const body = await request.json() as { title: string; plot_type: string; source: string; field_path: string };
          const created = {
            id: "score-plot",
            title: body.title,
            plot_type: body.plot_type,
            source: body.source,
            field_path: body.field_path,
            is_system_locked: false,
            iframe_url: "http://grafana.local/d-solo/score",
            created_at: "2026-04-01T10:10:00Z",
          };
          dashboards.push(created);
          return ok(created, 201);
        },
      },
    ]);

    renderApp("/deployments/fraud-prod");

    expect(await screen.findByText("Fraud Prod")).toBeInTheDocument();
    expect(screen.getByTitle("Latency")).toBeInTheDocument();
    expect(screen.getByTitle("Status codes")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "View schemas" }));
    const schemaDialog = screen.getByRole("dialog", { name: "Deployment schemas" });
    expect(schemaDialog).toBeInTheDocument();
    expect(within(schemaDialog).getByText(/"instances"/)).toBeInTheDocument();
    const writeText = vi.fn().mockRejectedValue(new Error("Clipboard blocked"));
    const execCommand = vi.fn().mockReturnValue(true);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    Object.defineProperty(document, "execCommand", {
      configurable: true,
      value: execCommand,
    });
    await userEvent.click(within(schemaDialog).getAllByRole("button", { name: "Copy" })[0]);
    expect(writeText).toHaveBeenCalledWith(expect.stringContaining('"instances"'));
    expect(execCommand).toHaveBeenCalledWith("copy");
    expect(within(schemaDialog).getByRole("button", { name: "Copied" })).toBeInTheDocument();
    await userEvent.click(schemaDialog);
    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: "Deployment schemas" })).not.toBeInTheDocument();
    });

    await userEvent.click(screen.getByRole("button", { name: "Field" }));
    expect(await screen.findByRole("option", { name: /instances\[\*\]\[\*\]/ })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /instances\[\*\]\[0\]/ })).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");

    await userEvent.type(screen.getByPlaceholderText("Prediction score distribution"), "Predictions over time");
    await userEvent.click(screen.getByRole("button", { name: "Source" }));
    await userEvent.click(screen.getByRole("option", { name: "Output" }));
    await userEvent.click(screen.getByRole("button", { name: "Field" }));
    await userEvent.click(screen.getByRole("option", { name: /predictions\[\*\]/ }));
    expect(screen.queryByRole("option", { name: "Time series" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Plot type" }));
    expect(screen.getByRole("option", { name: "Category counts over time" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("option", { name: "Category counts over time" }));
    await userEvent.click(screen.getByRole("button", { name: "Create plot" }));

    expect(await screen.findByTitle("Predictions over time")).toBeInTheDocument();
  });
});
