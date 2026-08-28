#!/usr/bin/env python3
"""Standalone VAO-Blender validator and runtime-plan compiler."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vao_blender.core.archive import ProgressRecord, validate_package  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--no-payload", action="store_true", help="Development-only: skip payload fixity"
    )
    parser.add_argument("--no-archive-hash", action="store_true")
    parser.add_argument("--show-progress", action="store_true")
    parser.add_argument("--include-paths", action="store_true")
    arguments = parser.parse_args()

    def progress(record: ProgressRecord) -> None:
        if arguments.show_progress:
            total = record.total_bytes or record.total_entries
            done = record.verified_bytes or record.completed_entries
            fraction = (done / total * 100.0) if total else 0.0
            print(
                f"\r{record.stage:14s} {fraction:6.2f}% {record.current_path[:60]}",
                end="",
                file=sys.stderr,
            )

    outcome = validate_package(
        arguments.package,
        progress=progress,
        verify_payload=not arguments.no_payload,
        hash_archive=not arguments.no_archive_hash,
    )
    if arguments.show_progress:
        print(file=sys.stderr)
    report = outcome.report(redact_paths=not arguments.include_paths)
    report["valid"] = outcome.is_valid
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if arguments.output:
        arguments.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0 if outcome.is_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
