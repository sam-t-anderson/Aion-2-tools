"""Run the same lint the release CI runs, inside the test suite.

CI's "Tests and lint" job runs `python -m pyflakes aion2calc tests`, and the
release job only runs after it passes. A lint error there (e.g. an f-string
with no placeholders) silently blocks every release until someone notices in
CI. Running it here means `pytest` — what a contributor runs locally — catches
that class of regression before it reaches the release pipeline.
"""
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def test_pyflakes_is_clean():
    if importlib.util.find_spec("pyflakes") is None:
        pytest.skip("pyflakes is not installed (it is in the dev/CI environment)")
    result = subprocess.run([sys.executable, "-m", "pyflakes", "aion2calc", "tests"],
                            cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, "pyflakes reported issues (this blocks the release CI):\n" + result.stdout + result.stderr
