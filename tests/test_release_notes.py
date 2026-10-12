"""The release-notes publisher (Release job in .github/workflows/ci.yml) picks the
RELEASE_NOTES.md section whose first line contains "(<version>)". If the current
__version__ has no such section, the publisher now emits a generic body instead of
silently using an unrelated (older) section. This test fails the build whenever a
version is bumped without adding its changelog entry, so that fallback stays a
safety net rather than the norm.
"""
import pathlib
import re

import aion2calc

ROOT = pathlib.Path(__file__).resolve().parents[1]
NOTES = ROOT / "packaging" / "RELEASE_NOTES.md"


def _sections(text):
    return [p for p in re.split(r"(?m)^(?=## )", text) if p.strip()]


def test_current_version_has_a_release_notes_section():
    version = aion2calc.__version__
    text = NOTES.read_text(encoding="utf-8")
    matches = [s for s in _sections(text) if f"({version})" in s.splitlines()[0]]
    assert matches, (
        f"packaging/RELEASE_NOTES.md has no section for v{version}. "
        f"Add a '## <title> ({version})' section before releasing so the "
        f"published notes match the version."
    )
    # Exactly one section per version keeps the publisher's choice unambiguous.
    assert len(matches) == 1, f"Multiple RELEASE_NOTES.md sections match v{version}"
