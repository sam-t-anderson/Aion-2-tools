"""The SHA-256 of a release's downloads, for players to compare with the file they downloaded.

    python tools/release_checksums.py VERSION FILE... [--sums SHA256SUMS.txt] [--notes release-notes.md]
                                      [--readme README.md] [--sums-url URL]

``--sums`` writes the checksums in ``sha256sum`` format (``sha256sum -c`` checks a download against it),
``--notes`` appends a table of them to the release notes, and ``--readme`` replaces README.md's block
between ``<!-- checksums:start -->`` and ``<!-- checksums:end -->`` with the same table for this release.
The release job runs it after the builds, so the values are those of the files the release publishes:
the Windows installer and app are signed before their checksums are taken.
"""
from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path

REPO = "https://github.com/sam-t-anderson/Aion-2-tools"
START, END = "<!-- checksums:start -->", "<!-- checksums:end -->"
#: the downloads in the order the README's install table lists them
ORDER = ("setup-", "windows-portable", "macos", "linux")


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _rank(name: str) -> tuple[int, str]:
    return next((i for i, part in enumerate(ORDER) if part in name), len(ORDER)), name


def entries(paths) -> list[tuple[str, str]]:
    """``(file name, SHA-256)`` for each download, installer first; a SHA256SUMS file is skipped."""
    rows = [(Path(p).name, digest(Path(p))) for p in paths if Path(p).name != "SHA256SUMS.txt"]
    return sorted(rows, key=lambda row: _rank(row[0]))


def sums_text(rows) -> str:
    return "".join(f"{sha}  {name}\n" for name, sha in rows)


def table(rows) -> str:
    return "| File | SHA-256 |\n|---|---|\n" + "".join(f"| `{name}` | `{sha}` |\n" for name, sha in rows)


def readme_block(version: str, rows, sums_url: str | None = None) -> str:
    tag = f"v{version}"
    head = f"Latest release: **[{tag}]({REPO}/releases/tag/{tag})**"
    if sums_url:
        head += f" · [SHA256SUMS.txt]({sums_url})"
    return f"{START}\n{head}\n\n{table(rows)}{END}"


def replace_block(text: str, block: str) -> str:
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.S)
    if len(pattern.findall(text)) != 1:
        raise ValueError(f"README must hold exactly one {START} … {END} block")
    return pattern.sub(lambda _: block, text)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("version")
    parser.add_argument("files", nargs="+")
    parser.add_argument("--sums", help="write SHA256SUMS in sha256sum format to this file")
    parser.add_argument("--notes", help="append a checksum table to these release notes")
    parser.add_argument("--readme", help="replace this README's checksum block")
    parser.add_argument("--sums-url", default=None,
                        help="link to the release's SHA256SUMS.txt (default: the release's own download)")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"\d+\.\d+\.\d+", args.version):
        parser.error("VERSION must look like 0.2.347")
    rows = entries(args.files)
    if not rows:
        parser.error("no files to checksum")
    if args.sums:
        Path(args.sums).write_text(sums_text(rows), encoding="utf-8", newline="\n")
    if args.notes:
        notes = Path(args.notes)
        text = notes.read_text(encoding="utf-8").rstrip("\n")
        notes.write_text(text + "\n\n### SHA-256\n\nCompare the file you downloaded with its value "
                         "(see [verify your download](" + REPO + "#verify-your-download)).\n\n" + table(rows),
                         encoding="utf-8", newline="\n")
    if args.readme:
        url = args.sums_url if args.sums_url is not None else f"{REPO}/releases/download/v{args.version}/SHA256SUMS.txt"
        readme = Path(args.readme)
        readme.write_text(replace_block(readme.read_text(encoding="utf-8"), readme_block(args.version, rows, url or None)),
                          encoding="utf-8", newline="\n")
    for name, sha in rows:
        print(f"{sha}  {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
