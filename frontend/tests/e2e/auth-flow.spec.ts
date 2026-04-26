import { test, expect } from "@playwright/test";

/**
 * Auth flow E2E smoke — tests the middleware 307 redirect for protected routes.
 * Runs against the Next.js dev server at http://localhost:3000.
 */
test.describe("Auth middleware", () => {
  test("anonymous visit to /dashboard redirects to /login", async ({ page }) => {
    // Navigate without cookies — middleware should redirect
    await page.goto("/dashboard");
    await expect(page).toHaveURL(/\/login/);
  });

  test("anonymous visit to /profile redirects to /login", async ({ page }) => {
    await page.goto("/profile");
    await expect(page).toHaveURL(/\/login/);
  });

  test("anonymous visit to /pipeline redirects to /login", async ({ page }) => {
    await page.goto("/pipeline");
    await expect(page).toHaveURL(/\/login/);
  });

  test("home page loads without redirect", async ({ page }) => {
    await page.goto("/");
    // Should NOT be redirected to /login
    await expect(page).not.toHaveURL(/\/login/);
  });
});
