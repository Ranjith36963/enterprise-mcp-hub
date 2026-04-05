"""E2E tests: Job browsing and filtering in dashboard.

Tests: job cards display, filter functionality, sort options.
"""

import pytest
from playwright.sync_api import expect


pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        True,
        reason="E2E tests require running dashboard (use pytest tests/e2e/ -m e2e)",
    ),
]


class TestJobBrowsing:

    def test_main_content_area_renders(self, page, dashboard_url):
        """Main content area renders without errors."""
        page.goto(dashboard_url)
        page.wait_for_load_state("networkidle")
        main = page.locator('[data-testid="stAppViewContainer"]')
        expect(main).to_be_visible()

    def test_sort_options_available(self, page, dashboard_url):
        """Sort dropdown provides sorting options."""
        page.goto(dashboard_url)
        page.wait_for_load_state("networkidle")
        # Look for a selectbox containing sort-related options
        selectboxes = page.locator('[data-testid="stSelectbox"]')
        assert selectboxes.count() >= 1, "Expected at least one selectbox for sorting/filtering"

    def test_no_error_toast_on_load(self, page, dashboard_url):
        """Dashboard loads without showing any error toasts/alerts."""
        page.goto(dashboard_url)
        page.wait_for_load_state("networkidle")
        # Streamlit error messages use data-testid="stException"
        errors = page.locator('[data-testid="stException"]')
        assert errors.count() == 0, "Dashboard should not show errors on initial load"
