import userEvent from "@testing-library/user-event";
import { screen, waitFor } from "@testing-library/react";

import { renderApp } from "@/test/render-app";
import { installMockFetch, ok } from "@/test/mock-api";

describe("auth flow", () => {
  it("registers, logs in, and redirects into the protected overview route", async () => {
    installMockFetch([
      { method: "POST", path: "/users:register", handler: () => ok({ email: "new@example.com", is_active: true, is_superuser: false, is_verified: true, created_at: "2026-04-01T10:00:00Z" }, 201) },
      { method: "POST", path: "/users:login", handler: () => ok({ access_token: "header.payload.signature", token_type: "bearer" }) },
      { method: "GET", path: "/users/me", handler: () => ok({ email: "new@example.com", is_active: true, is_superuser: false, is_verified: true, created_at: "2026-04-01T10:00:00Z" }) },
      { method: "GET", path: "/experiments", handler: () => ok([]) },
      { method: "GET", path: "/datasets", handler: () => ok([]) },
      { method: "GET", path: "/repositories", handler: () => ok([]) },
    ]);

    renderApp("/register");

    const emailInput = screen.getByRole("textbox", { name: /email/i });
    const passwordInput = document.querySelector('input[type="password"]') as HTMLInputElement | null;

    expect(passwordInput).not.toBeNull();

    await userEvent.type(emailInput, "new@example.com");
    await userEvent.type(passwordInput!, "Password123");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByText("A clean snapshot of the platform")).toBeInTheDocument();
    await waitFor(() => expect(window.location.pathname).toBe("/overview"));
  });
});
