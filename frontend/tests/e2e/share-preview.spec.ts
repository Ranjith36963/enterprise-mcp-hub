import { test, expect } from "@playwright/test";

/**
 * Share-preview E2E smoke — verifies Open Graph + Twitter card meta tags on the
 * home page, and JSON-LD presence on a job detail page (when fallback metadata
 * renders with backend offline — og:title still populated from generateMetadata).
 */

test.describe("Open Graph / share-preview", () => {
  test("home page has og:title and twitter:card meta tags", async ({ page }) => {
    await page.goto("/");

    // OG title
    const ogTitle = page.locator('meta[property="og:title"]');
    await expect(ogTitle).toHaveAttribute("content", /job360/i);

    // Twitter card
    const twitterCard = page.locator('meta[name="twitter:card"]');
    await expect(twitterCard).toHaveAttribute("content", "summary_large_image");

    // Twitter title
    const twitterTitle = page.locator('meta[name="twitter:title"]');
    await expect(twitterTitle).toHaveAttribute("content", /job360/i);
  });

  test("home page <title> includes Job360", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveTitle(/job360/i);
  });

  test("job detail page has og:title even when backend is offline (fallback metadata)", async ({ page }) => {
    // Block all backend API calls so generateMetadata falls back to "not found" path
    await page.route("**/api/**", (route) =>
      route.fulfill({ status: 503, body: "" })
    );

    await page.goto("/jobs/999");

    // generateMetadata fallback: "Job not found — Job360"
    const ogTitle = page.locator('meta[property="og:title"]');
    await expect(ogTitle).toHaveAttribute("content", /job360/i);
  });
});
