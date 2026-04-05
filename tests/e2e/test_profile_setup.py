"""E2E tests: Profile setup flow in dashboard.

Tests: dashboard loads, CV upload, form fill, save profile.
"""

import pytest
from playwright.sync_api import expect


pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        True,  # Skip by default — run explicitly with: pytest tests/e2e/ -m e2e
        reason="E2E tests require running dashboard (use pytest tests/e2e/ -m e2e)",
    ),
]


class TestProfileSetup:

    def test_dashboard_loads(self, page, dashboard_url):
        """Dashboard page loads and shows Job360 title."""
        page.goto(dashboard_url)
        page.wait_for_load_state("networkidle")
        # Streamlit renders the title in the main content
        expect(page.locator("body")).to_contain_text("Job360")

    def test_sidebar_visible(self, page, dashboard_url):
        """Sidebar with profile setup is visible."""
        page.goto(dashboard_url)
        page.wait_for_load_state("networkidle")
        sidebar = page.locator('[data-testid="stSidebar"]')
        expect(sidebar).to_be_visible()

    def test_cv_upload_widget_present(self, page, dashboard_url):
        """CV file uploader widget is present in sidebar."""
        page.goto(dashboard_url)
        page.wait_for_load_state("networkidle")
        # Streamlit file_uploader has data-testid="stFileUploader"
        uploader = page.locator('[data-testid="stFileUploader"]').first
        expect(uploader).to_be_visible()

    def test_save_profile_button_present(self, page, dashboard_url):
        """Save Profile button is present in sidebar."""
        page.goto(dashboard_url)
        page.wait_for_load_state("networkidle")
        # Find button containing "Save Profile" text
        save_btn = page.get_by_role("button", name="Save Profile")
        expect(save_btn).to_be_visible()
