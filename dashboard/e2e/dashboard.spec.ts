import { test, expect } from "@playwright/test";

test("dashboard smoke flow", async ({ page }) => {
  const keys = [
    {
      name: "sdk",
      prefix: "mlp_sdk",
      is_revoked: false,
      created_at: "2026-04-01T10:00:00Z",
    },
  ];
  const runDashboards = [
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

  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace(/^.*\/api\/v1/, "");

    const json = (body: unknown, status = 200) =>
      route.fulfill({
        status,
        contentType: "application/json",
        body: JSON.stringify(body),
      });

    if (request.method() === "POST" && path === "/users:login") {
      return json({ access_token: "header.payload.signature", token_type: "bearer" });
    }
    if (request.method() === "GET" && path === "/users/me") {
      return json({ email: "user@example.com", is_active: true, is_superuser: false, is_verified: true, created_at: "2026-04-01T10:00:00Z" });
    }
    if (request.method() === "GET" && path === "/experiments") {
      return json([
        { name: "Iris experiment", slug: "iris-exp", logged_data_template: ["loss"], created_at: "2026-04-01T10:00:00Z", labels: {}, run_count: 1, latest_run: null },
      ]);
    }
    if (request.method() === "GET" && path === "/datasets") {
      return json([
        { name: "Iris dataset", slug: "iris-dataset", version: 2, status: "READY", file_type: "parquet", created_at: "2026-04-01T10:00:00Z", labels: {} },
      ]);
    }
    if (request.method() === "GET" && path === "/repositories") {
      return json([{ name: "Iris models", slug: "iris-models", is_deleted: false, created_at: "2026-04-01T10:00:00Z", labels: {} }]);
    }
    if (request.method() === "GET" && path === "/experiments/iris-exp") {
      return json({ name: "Iris experiment", slug: "iris-exp", logged_data_template: ["loss"], created_at: "2026-04-01T10:00:00Z", labels: {}, run_count: 1, latest_run: null });
    }
    if (request.method() === "GET" && path === "/experiments/iris-exp/metrics") {
      return json({ metrics: ["loss"] });
    }
    if (request.method() === "GET" && path === "/experiments/iris-exp/runs") {
      return json([
        { experiment_slug: "iris-exp", run_number: 1, status: "COMPLETED", created_at: "2026-04-01T10:00:00Z", ended_at: "2026-04-01T10:10:00Z", dataset: { dataset_slug: "iris-dataset", version: 2 }, model: { repository_slug: "iris-models", version: "1.0" }, latest_metrics: { loss: 0.1 }, labels: {} },
      ]);
    }
    if (request.method() === "GET" && path === "/experiments/iris-exp/runs/1") {
      return json({ experiment_slug: "iris-exp", run_number: 1, status: "COMPLETED", created_at: "2026-04-01T10:00:00Z", ended_at: "2026-04-01T10:10:00Z", dataset: { dataset_slug: "iris-dataset", version: 2 }, model: { repository_slug: "iris-models", version: "1.0" }, latest_metrics: { loss: 0.1 }, labels: {} });
    }
    if (request.method() === "GET" && path === "/experiments/iris-exp/runs/1/plots/loss") {
      return json({ metric_name: "loss", points: [{ step: 1, val: 0.1, timestamp: "2026-04-01T10:01:00Z" }] });
    }
    if (request.method() === "GET" && path === "/experiments/iris-exp/runs/1/dashboards") {
      return json(runDashboards);
    }
    if (request.method() === "POST" && path === "/experiments/iris-exp/runs/1/dashboards") {
      const body = JSON.parse(request.postData() ?? "{}");
      const created = {
        id: "plot-2",
        title: body.title,
        plot_type: body.plot_type,
        metrics: body.metrics,
        display_order: runDashboards.length,
        iframe_url: "http://grafana.local/d-solo/accuracy",
        created_at: "2026-04-01T10:03:00Z",
      };
      runDashboards.push(created);
      return json(created, 201);
    }
    if (request.method() === "DELETE" && path === "/experiments/iris-exp/runs/1/dashboards/plot-2") {
      runDashboards.splice(
        runDashboards.findIndex((dashboard) => dashboard.id === "plot-2"),
        1,
      );
      return json(null, 204);
    }
    if (request.method() === "GET" && path === "/datasets/iris-dataset/versions/2") {
      return json({ name: "Iris dataset", slug: "iris-dataset", version: 2, status: "READY", file_type: "parquet", created_at: "2026-04-01T10:00:00Z", labels: {} });
    }
    if (request.method() === "GET" && path === "/repositories/iris-models") {
      return json({ name: "Iris models", slug: "iris-models", is_deleted: false, created_at: "2026-04-01T10:00:00Z", labels: {} });
    }
    if (request.method() === "GET" && path === "/repositories/iris-models/models") {
      return json([{ repository_slug: "iris-models", name: "Iris classifier", version: "1.0", run: { experiment_slug: "iris-exp", run_number: 1 }, is_deleted: false, s3_uri: null, status: "READY", created_at: "2026-04-01T10:00:00Z", labels: {} }]);
    }
    if (request.method() === "GET" && path === "/repositories/iris-models/models/1.0") {
      return json({ repository_slug: "iris-models", name: "Iris classifier", version: "1.0", run: { experiment_slug: "iris-exp", run_number: 1 }, is_deleted: false, s3_uri: null, status: "READY", created_at: "2026-04-01T10:00:00Z", labels: {} });
    }
    if (request.method() === "GET" && path === "/users/me/api-keys") {
      return json(keys);
    }
    if (request.method() === "POST" && path === "/users/me/api-keys") {
      return json({ name: "cli", prefix: "mlp_cli", is_revoked: false, created_at: "2026-04-02T10:00:00Z", api_key: "mlp_secret" }, 201);
    }

    return json({ detail: `Unhandled ${request.method()} ${path}` }, 500);
  });

  await page.goto("/login");
  await page.getByLabel("Email").fill("user@example.com");
  await page.getByLabel("Password").fill("Password123");
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page.getByText("A clean snapshot of the platform")).toBeVisible();
  const sidebar = page.locator("aside");

  await sidebar.getByRole("link", { name: "Experiments", exact: true }).click();
  await expect(page.getByText("Iris experiment")).toBeVisible();
  await page.getByText("Iris experiment").click();
  await expect(page.getByRole("link", { name: "Open run" })).toBeVisible();
  await page.locator('a[href="/experiments/iris-exp/runs/1"]').click();
  await expect(page).toHaveURL(/\/experiments\/iris-exp\/runs\/1$/);
  await expect(page.getByText("Run overview")).toBeVisible();
  await expect(page.getByText("Manage plots")).toBeVisible();
  await page.getByPlaceholder("Training loss").fill("Accuracy stat");
  await page.getByRole("button", { name: "Latest stat" }).click();
  await page.getByRole("button", { name: /loss/i }).click();
  await page.getByRole("button", { name: "Create plot" }).click();
  await expect(page.getByTitle("Accuracy stat")).toBeVisible();
  await sidebar.getByRole("link", { name: "Datasets", exact: true }).click();
  await page.getByRole("link", { name: "View latest" }).click();
  await expect(page.getByText("Download dataset")).toBeVisible();
  await sidebar.getByRole("link", { name: "Repositories", exact: true }).click();
  await page.getByText("Iris models").click();
  await page.getByText("Iris classifier").click();
  await expect(page.getByText("Download model artifact")).toBeVisible();
  await sidebar.getByRole("link", { name: "Account", exact: true }).click();
  await page.getByPlaceholder("sdk").fill("cli");
  await page.getByRole("button", { name: "Create API key" }).click();
  await expect(page.getByText("mlp_secret")).toBeVisible();
});
