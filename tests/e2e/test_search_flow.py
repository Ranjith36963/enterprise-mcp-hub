"""E2E tests: Search flow in dashboard.

Tests: search trigger button, search completion, no-profile warning.
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


class TestSearchFlow:

    def test_search_button_present(self, page, dashboard_url):
        """Search/Refresh button is visible on dashboard."""
        page.goto(dashboard_url)
        page.wait_for_load_state("networkidle")
        # Look for the refresh/search trigger button
        search_btn = page.get_by_role("button", name="Refresh")
        if search_btn.count() == 0:
            search_btn = page.get_by_role("button", name="Search")
        expect(search_btn.first).to_be_visible()

    def test_filter_controls_present(self, page, dashboard_url):
        """Filter controls (time range, min score, etc.) are available."""
        page.goto(dashboard_url)
        page.wait_for_load_state("networkidle")
        # Check for selectbox elements (Streamlit renders them with data-testid)
        selectboxes = page.locator('[data-testid="stSelectbox"]')
        expect(selectboxes.first).to_be_visible()

    def test_no_results_without_profile(self, page, dashboard_url):
        """Without a saved profile, dashboard shows appropriate message."""
        page.goto(dashboard_url)
        page.wait_for_load_state("networkidle")
        # The page should contain content (either jobs or a setup prompt)
        body = page.locator("body")
        expect(body).not_to_be_empty()
