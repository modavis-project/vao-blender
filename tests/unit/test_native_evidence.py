from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import scripts.native_evidence as native_evidence
from scripts.native_evidence import (
    assemble,
    merge_cells,
    publication_names,
    release_context,
    source_checkout_state,
    template,
    verify_publication,
    verify_tagged_source_binding,
)


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _base_release(directory: Path) -> dict:
    context = release_context()
    commit = "a" * 40
    release = context["release"]
    builder = release["builder"]
    for name in context["base_names"] - {
        "SHA256SUMS",
        "RELEASE_EVIDENCE.json",
        "release_metadata.toml",
    }:
        (directory / name).write_bytes(f"payload:{name}\n".encode())
    (directory / "release_metadata.toml").write_bytes(
        (native_evidence.ROOT / "release_metadata.toml").read_bytes()
    )
    records = [
        {
            "file": name,
            "kind": "unit-test-fixture",
            "bytes": (directory / name).stat().st_size,
            "sha256": _sha((directory / name).read_bytes()),
            **(
                {
                    "platforms": [
                        platform_name
                        for platform_name, artifact_name in context["artifact_names"].items()
                        if artifact_name == name
                    ]
                }
                if name in context["artifact_names"].values()
                else {}
            ),
        }
        for name in sorted(context["base_names"] - {"SHA256SUMS", "RELEASE_EVIDENCE.json"})
    ]
    evidence = {
        "extensionId": context["manifest"]["id"],
        "version": context["manifest"]["version"],
        "releaseLabel": release["release_label"],
        "releaseCommit": commit,
        "releaseStatus": release["status"],
        "releaseTag": release["release_tag"],
        "intendedReleaseTag": release["release_tag"],
        "releaseDOI": release["release_doi"],
        "releaseDate": release["release_date"],
        "blenderCompatibility": release["blender"],
        "platforms": release["blender"]["platforms"],
        "standards": release["vao_standard"],
        "nativeEvidenceRequired": release["native_evidence"],
        "splitPlatforms": True,
        "builder": {
            "blenderVersion": builder["blender_version"],
            "blenderVersionTuple": [5, 2, 1],
            "blenderBuildHash": builder["blender_build_hash"],
            "pythonVersion": builder["blender_python_version"],
            "pythonImplementation": "CPython",
            "system": builder["platform_system"],
            "machine": builder["platform_machine"],
            "blenderExecutableSha256": builder["blender_executable_sha256"],
            "driverPythonVersion": builder["driver_python_version"],
            "driverPythonImplementation": "CPython",
            "pinnedOfficialArchiveSha256": builder["official_archive_sha256"],
            "pinnedOfficialArchiveUrl": builder["official_archive_url"],
            "executableMatchesPinnedOfficialArchive": True,
            "archiveNormalization": ("sorted ZIP_STORED entries; 1980-01-01; POSIX 0644/0755"),
        },
        "filesExceptEvidenceAndChecksumList": records,
    }
    (directory / "RELEASE_EVIDENCE.json").write_text(json.dumps(evidence) + "\n", encoding="utf-8")
    checksums = "".join(
        f"{_sha((directory / name).read_bytes())}  {name}\n"
        for name in sorted(context["base_names"] - {"SHA256SUMS"})
    )
    (directory / "SHA256SUMS").write_text(checksums, encoding="ascii")
    return context


def _rewrite_evidence_and_checksums(directory: Path, evidence: dict) -> None:
    (directory / "RELEASE_EVIDENCE.json").write_text(json.dumps(evidence) + "\n", encoding="utf-8")
    names = {item.name for item in directory.iterdir()} - {
        "SHA256SUMS",
        "NATIVE_TEST_EVIDENCE.json",
        "PUBLICATION_SHA256SUMS",
    }
    (directory / "SHA256SUMS").write_text(
        "".join(f"{_sha((directory / name).read_bytes())}  {name}\n" for name in sorted(names)),
        encoding="ascii",
    )


class NativeEvidenceTests(unittest.TestCase):
    def setUp(self):
        self._temporary = tempfile.TemporaryDirectory()
        self.source_root = Path(self._temporary.name) / "source"
        self.source_root.mkdir()
        project_root = Path(__file__).resolve().parents[2]
        metadata = (project_root / "release_metadata.toml").read_text(encoding="utf-8")
        metadata = metadata.replace('status = "unreleased"', 'status = "prerelease"')
        metadata = metadata.replace('release_doi = ""', 'release_doi = "10.5281/zenodo.99999999"')
        metadata = metadata.replace('release_date = ""', 'release_date = "2026-08-31"')
        (self.source_root / "release_metadata.toml").write_text(metadata, encoding="utf-8")
        (self.source_root / "blender_manifest.toml").write_bytes(
            (project_root / "blender_manifest.toml").read_bytes()
        )
        self._root_patch = mock.patch("scripts.native_evidence.ROOT", self.source_root)
        self._git_patch = mock.patch(
            "scripts.native_evidence.source_checkout_state",
            return_value=("a" * 40, True),
        )
        self._tagged_binding_patch = mock.patch(
            "scripts.native_evidence.verify_tagged_source_binding"
        )
        self._root_patch.start()
        self._git_patch.start()
        self.tagged_binding_mock = self._tagged_binding_patch.start()

    def tearDown(self):
        self._tagged_binding_patch.stop()
        self._git_patch.stop()
        self._root_patch.stop()
        self._temporary.cleanup()

    def _completed_input(self, release_dir: Path) -> dict:
        data = template(release_dir)
        for index, cell in enumerate(data["cells"]):
            cell["status"] = "pass"
            cell["runUrl"] = (
                "https://github.com/modavis-project/vao-blender/actions/runs/123456789/attempts/2"
            )
            cell["observedAt"] = "2026-08-30T22:00:00Z"
            cell["blenderExecutableSha256"] = f"{index + 1:064x}"
            cell["runnerImageVersion"] = "20260830.1"
        return data

    def _tagged_binding_fixture(self, directory: Path) -> tuple[Path, dict, dict[str, str]]:
        release_dir = directory / "release"
        release_dir.mkdir()
        context = release_context()
        for filename in ("SBOM.spdx.json", "RELEASE_NOTES.md"):
            payload = f"tagged:{filename}\n".encode()
            (self.source_root / filename).write_bytes(payload)
            (release_dir / filename).write_bytes(payload)
        (release_dir / "release_metadata.toml").write_bytes(
            (self.source_root / "release_metadata.toml").read_bytes()
        )
        for platform_name, artifact_name in context["artifact_names"].items():
            (release_dir / artifact_name).write_bytes(f"artifact:{platform_name}\n".encode())
        source_archive_name = f"vao-blender-{context['release']['release_label']}-source.zip"
        (release_dir / source_archive_name).write_bytes(b"canonical source archive")
        checksums = {item.name: _sha(item.read_bytes()) for item in release_dir.iterdir()}
        return release_dir, context, checksums

    def test_detached_evidence_assembles_and_verifies_without_changing_base_files(self):
        with tempfile.TemporaryDirectory() as directory:
            release_dir = Path(directory) / "release"
            release_dir.mkdir()
            context = _base_release(release_dir)
            before = {name: (release_dir / name).read_bytes() for name in context["base_names"]}
            input_path = Path(directory) / "native-input.json"
            input_path.write_text(json.dumps(self._completed_input(release_dir)), encoding="utf-8")

            assemble(release_dir, input_path, overwrite=False)
            verify_publication(release_dir)

            self.assertEqual(
                {name: (release_dir / name).read_bytes() for name in context["base_names"]},
                before,
            )
            self.assertEqual(
                {item.name for item in release_dir.iterdir()}, publication_names(context)
            )

    def test_assembly_recovers_a_verified_base_backup_after_interrupted_rename(self):
        with tempfile.TemporaryDirectory() as directory:
            release_dir = Path(directory) / "release"
            release_dir.mkdir()
            _base_release(release_dir)
            input_path = Path(directory) / "native-input.json"
            input_path.write_text(json.dumps(self._completed_input(release_dir)), encoding="utf-8")
            backup = Path(directory) / ".release.previous-111"
            release_dir.rename(backup)

            assemble(release_dir, input_path, overwrite=False)

            self.assertTrue(release_dir.is_dir())
            self.assertFalse(backup.exists())
            verify_publication(release_dir)

    def test_verifier_recovers_a_publication_backup_with_its_outer_inventory(self):
        with tempfile.TemporaryDirectory() as directory:
            release_dir = Path(directory) / "release"
            release_dir.mkdir()
            _base_release(release_dir)
            input_path = Path(directory) / "native-input.json"
            input_path.write_text(json.dumps(self._completed_input(release_dir)), encoding="utf-8")
            assemble(release_dir, input_path, overwrite=False)
            backup = Path(directory) / ".release.previous-222"
            release_dir.rename(backup)

            verify_publication(release_dir)

            self.assertTrue(release_dir.is_dir())
            self.assertFalse(backup.exists())

    def test_native_recovery_preserves_both_generations_for_manual_review(self):
        with tempfile.TemporaryDirectory() as directory:
            release_dir = Path(directory) / "release"
            release_dir.mkdir()
            _base_release(release_dir)
            input_path = Path(directory) / "native-input.json"
            input_path.write_text(json.dumps(self._completed_input(release_dir)), encoding="utf-8")
            assemble(release_dir, input_path, overwrite=False)
            backup = Path(directory) / ".release.previous-333"
            backup.mkdir()

            with self.assertRaisesRegex(RuntimeError, "manual recovery"):
                verify_publication(release_dir)

            self.assertTrue(release_dir.is_dir())
            self.assertTrue(backup.is_dir())

    def test_source_checkout_requires_an_annotated_tag_at_head(self):
        repository = Path(self._temporary.name) / "repository"
        repository.mkdir()
        commands = (
            ("git", "init", "-q"),
            ("git", "config", "user.name", "VAO Test"),
            ("git", "config", "user.email", "vao@example.invalid"),
        )
        for command in commands:
            subprocess.run(command, cwd=repository, check=True)
        (repository / "tracked.txt").write_text("tracked\n", encoding="utf-8")
        subprocess.run(("git", "add", "tracked.txt"), cwd=repository, check=True)
        subprocess.run(("git", "commit", "-q", "-m", "fixture"), cwd=repository, check=True)
        subprocess.run(("git", "tag", "v-test"), cwd=repository, check=True)
        with mock.patch("scripts.native_evidence.ROOT", repository):
            with self.assertRaisesRegex(RuntimeError, "annotated release-tag"):
                source_checkout_state("v-test")
        subprocess.run(("git", "tag", "-d", "v-test"), cwd=repository, check=True)
        subprocess.run(
            ("git", "tag", "-a", "v-test", "-m", "annotated fixture"),
            cwd=repository,
            check=True,
        )
        head = subprocess.run(
            ("git", "rev-parse", "HEAD"),
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        with mock.patch("scripts.native_evidence.ROOT", repository):
            self.assertEqual(source_checkout_state("v-test"), (head, True))

    def test_template_invokes_exact_tagged_source_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            release_dir = Path(directory) / "release"
            release_dir.mkdir()
            _base_release(release_dir)

            template(release_dir)

            self.tagged_binding_mock.assert_called_once()
            call = self.tagged_binding_mock.call_args
            self.assertEqual(call.args, (release_dir,))
            self.assertEqual(call.kwargs["context"]["release"]["release_tag"], "v0.4.0-rc.1")
            self.assertEqual(
                set(call.kwargs["checksums"]),
                release_context()["base_names"] - {"SHA256SUMS"},
            )

    def test_tagged_source_binding_revalidates_every_source_derived_member(self):
        with tempfile.TemporaryDirectory() as directory:
            release_dir, context, checksums = self._tagged_binding_fixture(Path(directory))
            tracked_members = set(native_evidence.DETACHED_SOURCE_MEMBERS) | {
                "tracked/source/member"
            }
            artifact_platforms = {
                artifact_name: platform_name
                for platform_name, artifact_name in context["artifact_names"].items()
            }

            def validate_artifact(artifact: Path, **_kwargs):
                return [artifact_platforms[artifact.name]]

            def reconstruct_source(_root, _revision, _label, destination):
                destination.write_bytes(b"canonical source archive")

            with (
                mock.patch(
                    "scripts.native_evidence.git_tracked_files",
                    return_value=tracked_members,
                ) as tracked_call,
                mock.patch(
                    "scripts.native_evidence.verify_artifact_contents",
                    side_effect=validate_artifact,
                ) as artifact_call,
                mock.patch(
                    "scripts.native_evidence.create_source_archive",
                    side_effect=reconstruct_source,
                ) as source_call,
            ):
                verify_tagged_source_binding(
                    release_dir,
                    context=context,
                    checksums=checksums,
                )

            tracked_call.assert_called_once_with(self.source_root)
            self.assertEqual(artifact_call.call_count, len(context["artifact_names"]))
            for call in artifact_call.call_args_list:
                self.assertEqual(call.kwargs["source_root"], self.source_root)
                self.assertEqual(call.kwargs["tracked_members"], tracked_members)
                self.assertTrue(call.kwargs["split"])
                self.assertEqual(
                    call.kwargs["expected_platforms"],
                    set(context["manifest"]["platforms"]),
                )
            source_call.assert_called_once()
            self.assertEqual(
                source_call.call_args.args[:3],
                (
                    self.source_root,
                    context["release"]["release_tag"],
                    context["release"]["release_label"],
                ),
            )

    def test_tagged_source_binding_rejects_changed_detached_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            release_dir, context, checksums = self._tagged_binding_fixture(Path(directory))
            (release_dir / "SBOM.spdx.json").write_bytes(b"changed")
            artifact_platforms = {
                artifact_name: platform_name
                for platform_name, artifact_name in context["artifact_names"].items()
            }
            with (
                mock.patch(
                    "scripts.native_evidence.git_tracked_files",
                    return_value=set(native_evidence.DETACHED_SOURCE_MEMBERS),
                ),
                mock.patch(
                    "scripts.native_evidence.verify_artifact_contents",
                    side_effect=lambda artifact, **_kwargs: [artifact_platforms[artifact.name]],
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "detached SBOM.spdx.json differs"):
                    verify_tagged_source_binding(
                        release_dir,
                        context=context,
                        checksums=checksums,
                    )

    def test_tagged_source_binding_rejects_untracked_detached_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            release_dir, context, checksums = self._tagged_binding_fixture(Path(directory))
            with (
                mock.patch("scripts.native_evidence.git_tracked_files", return_value=set()),
                mock.patch("scripts.native_evidence.verify_artifact_contents") as artifact_call,
            ):
                with self.assertRaisesRegex(RuntimeError, "not fully tracked"):
                    verify_tagged_source_binding(
                        release_dir,
                        context=context,
                        checksums=checksums,
                    )
            artifact_call.assert_not_called()

    def test_tagged_source_binding_rejects_reconstructed_source_difference(self):
        with tempfile.TemporaryDirectory() as directory:
            release_dir, context, checksums = self._tagged_binding_fixture(Path(directory))
            artifact_platforms = {
                artifact_name: platform_name
                for platform_name, artifact_name in context["artifact_names"].items()
            }

            def reconstruct_changed(_root, _revision, _label, destination):
                destination.write_bytes(b"different tagged source archive")

            with (
                mock.patch(
                    "scripts.native_evidence.git_tracked_files",
                    return_value=set(native_evidence.DETACHED_SOURCE_MEMBERS),
                ),
                mock.patch(
                    "scripts.native_evidence.verify_artifact_contents",
                    side_effect=lambda artifact, **_kwargs: [artifact_platforms[artifact.name]],
                ),
                mock.patch(
                    "scripts.native_evidence.create_source_archive",
                    side_effect=reconstruct_changed,
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "reconstructed exact tagged source"):
                    verify_tagged_source_binding(
                        release_dir,
                        context=context,
                        checksums=checksums,
                    )

    def test_wrong_artifact_digest_cannot_be_attested(self):
        with tempfile.TemporaryDirectory() as directory:
            release_dir = Path(directory) / "release"
            release_dir.mkdir()
            _base_release(release_dir)
            data = self._completed_input(release_dir)
            data["cells"][0]["artifactSha256"] = "0" * 64
            input_path = Path(directory) / "native-input.json"
            input_path.write_text(json.dumps(data), encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "immutable pass validation"):
                assemble(release_dir, input_path, overwrite=False)
            self.assertFalse((release_dir / "NATIVE_TEST_EVIDENCE.json").exists())

    def test_independent_cell_files_merge_only_as_an_exact_complete_matrix(self):
        with tempfile.TemporaryDirectory() as directory:
            release_dir = Path(directory) / "release"
            input_dir = Path(directory) / "cells"
            release_dir.mkdir()
            input_dir.mkdir()
            _base_release(release_dir)
            completed = self._completed_input(release_dir)
            for index, cell in enumerate(completed["cells"]):
                (input_dir / f"cell-{index}.json").write_text(json.dumps(cell), encoding="utf-8")

            self.assertEqual(merge_cells(release_dir, input_dir), completed)

            (input_dir / "cell-0.json").unlink()
            with self.assertRaisesRegex(RuntimeError, "missing cells"):
                merge_cells(release_dir, input_dir)

    def test_run_url_must_identify_this_repository_actions_run(self):
        with tempfile.TemporaryDirectory() as directory:
            release_dir = Path(directory) / "release"
            release_dir.mkdir()
            _base_release(release_dir)
            data = self._completed_input(release_dir)
            data["cells"][0]["runUrl"] = "https://ci.example.test/runs/1"
            input_path = Path(directory) / "native-input.json"
            input_path.write_text(json.dumps(data), encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "immutable pass validation"):
                assemble(release_dir, input_path, overwrite=False)

    def test_cells_cannot_mix_workflow_run_attempts(self):
        with tempfile.TemporaryDirectory() as directory:
            release_dir = Path(directory) / "release"
            release_dir.mkdir()
            _base_release(release_dir)
            data = self._completed_input(release_dir)
            data["cells"][0]["runUrl"] = (
                "https://github.com/modavis-project/vao-blender/actions/runs/123456789/attempts/1"
            )
            input_path = Path(directory) / "native-input.json"
            input_path.write_text(json.dumps(data), encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "one workflow run attempt"):
                assemble(release_dir, input_path, overwrite=False)

    def test_publication_verifier_detects_post_attestation_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            release_dir = Path(directory) / "release"
            release_dir.mkdir()
            context = _base_release(release_dir)
            input_path = Path(directory) / "native-input.json"
            input_path.write_text(json.dumps(self._completed_input(release_dir)), encoding="utf-8")
            assemble(release_dir, input_path, overwrite=False)
            artifact = release_dir / next(iter(context["artifact_names"].values()))
            artifact.write_bytes(b"tampered")

            with self.assertRaisesRegex(RuntimeError, "verification failed"):
                verify_publication(release_dir)

    def test_unreleased_null_tag_staging_base_cannot_be_attested(self):
        with tempfile.TemporaryDirectory() as directory:
            release_dir = Path(directory) / "release"
            release_dir.mkdir()
            _base_release(release_dir)
            completed = self._completed_input(release_dir)
            evidence_path = release_dir / "RELEASE_EVIDENCE.json"
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence.update(
                {
                    "releaseStatus": "unreleased",
                    "releaseTag": None,
                    "releaseDOI": None,
                    "releaseDate": None,
                }
            )
            _rewrite_evidence_and_checksums(release_dir, evidence)

            with self.assertRaisesRegex(RuntimeError, "not final or canonical"):
                template(release_dir)
            input_path = Path(directory) / "completed.json"
            input_path.write_text(json.dumps(completed), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "not final or canonical"):
                assemble(release_dir, input_path, overwrite=False)

    def test_publication_verifier_rechecks_final_base_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            release_dir = Path(directory) / "release"
            release_dir.mkdir()
            _base_release(release_dir)
            input_path = Path(directory) / "completed.json"
            input_path.write_text(json.dumps(self._completed_input(release_dir)), encoding="utf-8")
            assemble(release_dir, input_path, overwrite=False)

            evidence_path = release_dir / "RELEASE_EVIDENCE.json"
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence.update({"releaseStatus": "unreleased", "releaseTag": None})
            _rewrite_evidence_and_checksums(release_dir, evidence)
            attestation_path = release_dir / "NATIVE_TEST_EVIDENCE.json"
            attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
            attestation["baseChecksumsSha256"] = _sha((release_dir / "SHA256SUMS").read_bytes())
            attestation_path.write_text(json.dumps(attestation), encoding="utf-8")
            publication_names = {item.name for item in release_dir.iterdir()} - {
                "PUBLICATION_SHA256SUMS"
            }
            (release_dir / "PUBLICATION_SHA256SUMS").write_text(
                "".join(
                    f"{_sha((release_dir / name).read_bytes())}  {name}\n"
                    for name in sorted(publication_names)
                ),
                encoding="ascii",
            )

            with self.assertRaisesRegex(RuntimeError, "not final or canonical"):
                verify_publication(release_dir)


if __name__ == "__main__":
    unittest.main()
