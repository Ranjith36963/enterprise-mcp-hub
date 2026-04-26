import { test, expect } from "@playwright/test";

/**
 * Pipeline page E2E smoke — checks that:
 * 1. Unauthenticated visit to /pipeline redirects to /login (middleware).
 * 2. Authenticated visit with mocked pipeline API shows the Kanban board.
 */

const MOCK_APPLICATIONS = {
  applications: [
    {
      id: 1,
      job_id: 42,
      user_id: "test-user-id",
      stage: "applied",
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      notes: null,
      reminder_at: null,
      title: "ML Engineer",
      company: "TechCo",
      apply_url: "https://example.com",
      salary: null,
    },
  ],
};

test.describe("Pipeline page", () => {
  test("anonymous visit redirects to /login", async ({ page }) => {
    await page.goto("/pipeline");
    await expect(page).toHaveURL(/\/login/);
  });

  test("authenticated visit shows pipeline heading", async ({
    page,
    context,
  }) => {
    await context.addCookies([
      {
        name: "job360_session",
        value: "smoke-test-token",
        domain: "localhost",
        path: "/",
      },
    ]);

    await page.route("**/api/pipeline**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MOCK_APPLICATIONS),
      })
    );

    await page.goto("/pipeline");
    await expect(page).not.toHaveURL(/\/login/);

    // Pipeline heading
    await expect(
      page.getByRole("heading", { name: /pipeline/i })
    ).toBeVisible({ timeout: 10_000 });
  });

  test("applied card appears in the pipeline board", async ({
    page,
    context,
  }) => {
    await context.addCookies([
      {
        name: "job360_session",
        value: "smoke-test-token",
        domain: "localhost",
        path: "/",
      },
    ]);

    await page.route("**/api/pipeline**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MOCK_APPLICATIONS),
      })
    );

    await page.goto("/pipeline");

    // The mocked job title should appear in the board
    await expect(page.getByText("ML Engineer")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText("TechCo")).toBeVisible();
  });
});
