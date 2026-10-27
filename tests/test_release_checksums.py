"""The release's SHA-256 values (tools/release_checksums.py, run by the Release job in .github/workflows/ci.yml):
SHA256SUMS.txt in sha256sum's own format, the same table appended to the release notes, and README.md's
"Verify your download" block replaced with the release's values, installer first."""
import hashlib
import pathlib
import re
import shutil
import subprocess
import sys

import pytest

import aion2calc

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import release_checksums as rc  # noqa: E402

FILES = {"aion2calc-0.2.400-linux.tar.gz": b"linux", "aion2calc-0.2.400-macos.zip": b"mac",
         "aion2calc-setup-0.2.400.exe": b"setup", "aion2calc-0.2.400-windows-portable.zip": b"portable"}


def _release(tmp_path):
    folder = tmp_path / "assets"
    folder.mkdir()
    for name, data in FILES.items():
        (folder / name).write_bytes(data)
    return folder


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def test_checksums_list_the_installer_first_and_skip_an_existing_sums_file(tmp_path):
    folder = _release(tmp_path)
    (folder / "SHA256SUMS.txt").write_text("old\n")
    rows = rc.entries(sorted(folder.iterdir()))
    assert [name for name, _ in rows] == ["aion2calc-setup-0.2.400.exe", "aion2calc-0.2.400-windows-portable.zip",
                                          "aion2calc-0.2.400-macos.zip", "aion2calc-0.2.400-linux.tar.gz"]
    assert dict(rows) == {name: _sha(data) for name, data in FILES.items()}


def test_the_release_files_notes_and_readme_get_the_same_values(tmp_path):
    folder = _release(tmp_path)
    notes = tmp_path / "release-notes.md"
    notes.write_text("## Something new (0.2.400)\n\nIt works.\n", encoding="utf-8")
    readme = tmp_path / "README.md"
    readme.write_text("# Title\n\n<!-- checksums:start -->\nold table\n<!-- checksums:end -->\n\nAfter.\n", encoding="utf-8")
    sums = folder / "SHA256SUMS.txt"
    assert rc.main(["0.2.400", *map(str, sorted(folder.glob("aion2calc-*"))),
                    "--sums", str(sums), "--notes", str(notes), "--readme", str(readme)]) == 0
    lines = sums.read_text(encoding="utf-8").splitlines()
    assert lines[0] == f"{_sha(b'setup')}  aion2calc-setup-0.2.400.exe" and len(lines) == 4
    if shutil.which("sha256sum"):                     # sha256sum itself checks the release's files against it
        subprocess.run(["sha256sum", "-c", "SHA256SUMS.txt"], cwd=folder, check=True, capture_output=True)
    text = notes.read_text(encoding="utf-8")
    assert text.startswith("## Something new (0.2.400)\n\nIt works.\n\n### SHA-256\n")
    assert f"| `aion2calc-0.2.400-macos.zip` | `{_sha(b'mac')}` |" in text
    block = readme.read_text(encoding="utf-8")
    assert "old table" not in block and block.startswith("# Title\n\n<!-- checksums:start -->\n") and block.endswith("\n\nAfter.\n")
    assert "**[v0.2.400](https://github.com/sam-t-anderson/Aion-2-tools/releases/tag/v0.2.400)**" in block
    assert "[SHA256SUMS.txt](https://github.com/sam-t-anderson/Aion-2-tools/releases/download/v0.2.400/SHA256SUMS.txt)" in block
    assert f"| `aion2calc-setup-0.2.400.exe` | `{_sha(b'setup')}` |" in block


def test_a_release_without_a_sums_file_links_none(tmp_path):
    folder = _release(tmp_path)
    readme = tmp_path / "README.md"
    readme.write_text("<!-- checksums:start --><!-- checksums:end -->", encoding="utf-8")
    rc.main(["0.2.400", *map(str, folder.iterdir()), "--readme", str(readme), "--sums-url", ""])
    assert "SHA256SUMS.txt" not in readme.read_text(encoding="utf-8")


def test_a_readme_without_exactly_one_block_is_refused():
    with pytest.raises(ValueError):
        rc.replace_block("no markers", "x")
    twice = "<!-- checksums:start -->a<!-- checksums:end --><!-- checksums:start -->b<!-- checksums:end -->"
    with pytest.raises(ValueError):
        rc.replace_block(twice, "x")
    with pytest.raises(SystemExit):
        rc.main(["latest", "x"])                      # not a version


def test_the_readme_lists_a_released_version_with_every_download():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    block = re.search(r"<!-- checksums:start -->(.*?)<!-- checksums:end -->", text, re.S).group(1)
    version = re.search(r"\*\*\[v(\d+\.\d+\.\d+)\]", block).group(1)
    assert tuple(map(int, version.split("."))) <= tuple(map(int, aion2calc.__version__.split(".")))
    rows = re.findall(r"\| `([^`]+)` \| `([0-9a-f]{64})` \|", block)
    assert [name for name, _ in rows] == [f"aion2calc-setup-{version}.exe", f"aion2calc-{version}-windows-portable.zip",
                                          f"aion2calc-{version}-macos.zip", f"aion2calc-{version}-linux.tar.gz"]
