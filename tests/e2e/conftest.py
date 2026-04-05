"""Playwright E2E test fixtures for Job360 dashboard.

Launches a Streamlit server on a free port, waits for it to be ready,
then provides a browser page fixture for each test.
"""

import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DASHBOARD_PATH = PROJECT_ROOT / "src" / "dashboard.py"
TEST_CV_DIR = PROJECT_ROOT / "tests" / "qa_profiles" / "pdfs"


def _find_free_port() -> int:
    """Find a free TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _wait_for_server(port: int, timeout: int = 30) -> bool:
    """Poll until Streamlit server responds on port."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("localhost", port), timeout=2):
                return True
        except (ConnectionRefusedError, OSError):
            time.sleep(1)
    return False


@pytest.fixture(scope="session")
def dashboard_url():
    """Launch Streamlit dashboard and yield its URL. Tears down on session end."""
    port = _find_free_port()
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "streamlit", "run",
            str(DASHBOARD_PATH),
            "--server.port", str(port),
            "--server.headless", "true",
            "--browser.gatherUsageStats", "false",
            "--server.fileWatcherType", "none",
        ],
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if not _wait_for_server(port):
        proc.kill()
        pytest.skip("Streamlit dashboard failed to start within 30s")

    url = f"http://localhost:{port}"
    yield url

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture
def test_cv_path():
    """Return path to a test CV PDF for upload tests."""
    # Use data_scientist.pdf as default test CV
    cv = TEST_CV_DIR / "data_scientist.pdf"
    if not cv.exists():
        # Fallback to any available PDF
        pdfs = list(TEST_CV_DIR.glob("*.pdf"))
        if pdfs:
            return pdfs[0]
        pytest.skip("No test CV PDFs available in tests/qa_profiles/pdfs/")
    return cv
