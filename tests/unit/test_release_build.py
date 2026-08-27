from __future__ import annotations

import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.build_extension import normalize_archive


class ReproducibleReleaseTests(unittest.TestCase):
    def test_zip_normalization_removes_order_and_timestamp_variance(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.zip"
            second = Path(directory) / "second.zip"
            with zipfile.ZipFile(first, "w") as archive:
                archive.writestr(
                    zipfile.ZipInfo("z.txt", (2026, 8, 27, 12, 30, 0)),
                    b"last",
                    compress_type=zipfile.ZIP_DEFLATED,
                )
                archive.writestr(
                    zipfile.ZipInfo("a.txt", (2026, 8, 27, 12, 31, 0)),
                    b"first",
                    compress_type=zipfile.ZIP_STORED,
                )
            with zipfile.ZipFile(second, "w") as archive:
                archive.writestr(
                    zipfile.ZipInfo("a.txt", (2020, 1, 2, 3, 4, 6)),
                    b"first",
                    compress_type=zipfile.ZIP_STORED,
                )
                archive.writestr(
                    zipfile.ZipInfo("z.txt", (2020, 1, 2, 3, 5, 6)),
                    b"last",
                    compress_type=zipfile.ZIP_DEFLATED,
                )

            normalize_archive(first)
            normalize_archive(second)

            self.assertEqual(
                hashlib.sha256(first.read_bytes()).digest(),
                hashlib.sha256(second.read_bytes()).digest(),
            )
            with zipfile.ZipFile(first) as archive:
                self.assertEqual(archive.namelist(), ["a.txt", "z.txt"])
                self.assertTrue(
                    all(item.date_time == (1980, 1, 1, 0, 0, 0) for item in archive.infolist())
                )
                self.assertEqual(archive.read("a.txt"), b"first")
                self.assertEqual(archive.read("z.txt"), b"last")


if __name__ == "__main__":
    unittest.main()
