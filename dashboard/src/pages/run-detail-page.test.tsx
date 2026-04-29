import userEvent from "@testing-library/user-event";
import { screen } from "@testing-library/react";

import { writeToken } from "@/lib/auth-storage";
import { renderApp } from "@/test/render-app";
import { installMockFetch, ok } from "@/test/mock-api";

describe("run detail page", () => {
  it("renders saved run plots and manages them through the new builder", async () => {
    writeToken("header.payload.signature");
    const dashboards: Array<{
      id: string;
      title: string;
      plot_type: "line" | "stat";
      metrics: string[];
      display_order: number;
      iframe_url: string;
      created_at: string;
    }> = [
      {
        id: "plot-1",
        title: "Loss curve",
        plot_type: "line",
        metrics: ["loss"],
        display_order: 0,
        iframe_url: "http://grafana.local/d-solo/loss",
        created_at: "2026-04-01T10:00:00Z",
      },
    ];

    installMockFetch([
      { method: "GET", path: "/users/me", handler: () => ok({ email: "user@example.com", is_active: true, is_superuser: false, is_verified: true, created_at: "2026-04-01T10:00:00Z" }) },
      {
        method: "GET",
        path: "/experiments/iris-exp/runs/3",
        handler: () =>
          ok({
            experiment_slug: "iris-exp",
            run_number: 3,
            status: "COMPLETED",
            created_at: "2026-04-01T10:00:00Z",
            ended_at: "2026-04-01T10:10:00Z",
            dataset: { dataset_slug: "iris-dataset", version: 2 },
            model: { repository_slug: "iris-models", version: "1.0.0" },
            latest_metrics: { loss: 0.1 },
            labels: { gpu: "t4" },
          }),
      },
      { method: "GET", path: "/experiments/iris-exp/metrics", handler: () => ok({ metrics: ["loss"] }) },
      { method: "GET", path: "/experiments/iris-exp/runs/3/dashboards", handler: () => ok(dashboards) },
      {
        method: "POST",
        path: "/experiments/iris-exp/runs/3/dashboards",
        handler: async (request) => {
          const payload = (await request.json()) as { title: string; plot_type: "line" | "stat"; metrics: string[] };
          const created = {
            id: "plot-2",
            title: payload.title,
            plot_type: payload.plot_type,
            metrics: payload.metrics,
            display_order: dashboards.length,
            iframe_url: "http://grafana.local/d-solo/accuracy",
            created_at: "2026-04-01T10:05:00Z",
          };
          dashboards.push(created);
          return ok(created, 201);
        },
      },
      {
        method: "PATCH",
        path: "/experiments/iris-exp/runs/3/dashboards/plot-1",
        handler: async (request) => {
          const payload = (await request.json()) as Partial<{
            title: string;
            plot_type: "line" | "stat";
            metrics: string[];
            display_order: number;
          }>;
          dashboards[0] = {
            ...dashboards[0],
            ...payload,
          };
          return ok(dashboards[0]);
        },
      },
      {
        method: "DELETE",
        path: "/experiments/iris-exp/runs/3/dashboards/plot-2",
        handler: () => {
          dashboards.splice(
            dashboards.findIndex((dashboard) => dashboard.id === "plot-2"),
            1,
          );
          return ok(null, 204);
        },
      },
    ]);

    const rendered = renderApp("/experiments/iris-exp/runs/3");

    expect(await screen.findByText("Run 3")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /attached dataset/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /produced model/i })).toBeInTheDocument();
    const initialFrame = screen.getByTitle("Loss curve");
    const initialFrameSrc = initialFrame.getAttribute("src");
    expect(initialFrame).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Edit" }));
    await userEvent.clear(screen.getByPlaceholderText("Training loss"));
    await userEvent.type(screen.getByPlaceholderText("Training loss"), "Loss latest");
    await userEvent.click(screen.getByRole("button", { name: "Latest stat" }));
    await userEvent.click(screen.getByRole("button", { name: "Update plot" }));

    const updatedFrame = await screen.findByTitle("Loss latest");
    expect(updatedFrame.getAttribute("src")).not.toEqual(initialFrameSrc);

    await userEvent.type(screen.getByPlaceholderText("Training loss"), "Accuracy stat");
    await userEvent.click(screen.getByRole("button", { name: "Latest stat" }));
    await userEvent.click(screen.getByRole("button", { name: /loss/i }));
    await userEvent.click(screen.getByRole("button", { name: "Create plot" }));

    expect(await screen.findByTitle("Accuracy stat")).toBeInTheDocument();

    rendered.unmount();
    renderApp("/experiments/iris-exp/runs/3");
    expect(await screen.findByTitle("Accuracy stat")).toBeInTheDocument();

    const deleteButtons = await screen.findAllByRole("button", { name: "Delete" });
    await userEvent.click(deleteButtons[1]);
    expect(await screen.findByTitle("Loss latest")).toBeInTheDocument();
  });
});
