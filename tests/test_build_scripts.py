import subprocess
import pytest
from pathlib import Path

BUILD_SCRIPTS = [
    "build_html.py",
    "build_alignments_html.py",
    "build_charts_page.py",
    "build_soulmates_html.py",
]

@pytest.mark.parametrize("script", BUILD_SCRIPTS)
def test_build_script_runs(script):
    """Smoke test to ensure build scripts run without error."""
    result = subprocess.run(["python", script], capture_output=True, text=True)
    assert result.returncode == 0, f"{script} failed with error: {result.stderr}"
