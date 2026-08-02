"""Generate synthetic encrypted archive fixtures for Windows desktop tests.

The fixtures contain only deterministic synthetic text. Archive encryption metadata uses
library-generated salts, so archive bytes may change between regenerations.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import py7zr
import pyzipper

PASSWORD = "synthetic-password"
ENTRY_NAME = "folder/synthetic-content.txt"
CONTENT = b"Password Detective synthetic encrypted archive fixture.\n"


def generate(output_directory: Path) -> None:
    output_directory.mkdir(parents=True, exist_ok=True)

    zip_path = output_directory / "encrypted-valid.zip"
    with pyzipper.AESZipFile(
        zip_path,
        mode="w",
        compression=pyzipper.ZIP_DEFLATED,
        encryption=pyzipper.WZ_AES,
    ) as archive:
        archive.setpassword(PASSWORD.encode("utf-8"))
        archive.setencryption(pyzipper.WZ_AES, nbits=256)
        archive.writestr(ENTRY_NAME, CONTENT)

    seven_zip_path = output_directory / "encrypted-valid.7z"
    with py7zr.SevenZipFile(
        seven_zip_path,
        mode="w",
        password=PASSWORD,
        header_encryption=True,
    ) as archive:
        archive.writestr(CONTENT, ENTRY_NAME)

    print(f"Generated {zip_path}")
    print(f"Generated {seven_zip_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "apps"
        / "desktop-windows.tests"
        / "Fixtures",
    )
    arguments = parser.parse_args()
    generate(arguments.output.resolve())


if __name__ == "__main__":
    main()
