#!/usr/bin/env python3
# Copyright 2026 RioPlay
# SPDX-License-Identifier: MIT
"""Validated returns, selection continuity, and cold-sandbox handoffs."""
from contextlib import redirect_stderr, redirect_stdout
import errno
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("cpc", ROOT / "bin/cpc.py")
cpc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cpc)


class HandoffTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="cpc-handoff-test-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.source = self.root / "Project"
        self.source.mkdir()
        (self.source / "empty").mkdir()
        (self.source / "main.txt").write_bytes(b"original\n")
        (self.source / "keep.txt").write_bytes(b"explicit include\n")
        (self.source / "omit.secret").write_bytes(b"deliberately excluded\n")
        (self.source / ".cpcignore").write_bytes(b"keep.txt\n")

    def test_named_versioned_handoff_and_independent_validation(self):
        output = self.root / "return"
        result = cpc.handoff(self.source, output, "PortAtlas", "1.2.8",
                             includes=["keep.txt"], excludes=["*.secret"])
        self.assertEqual({p.name for p in output.iterdir()},
                         {"PortAtlas-1.2.8.cpc.md", "HANDOFF.md", "VALIDATION.json"})
        capsule = output / "PortAtlas-1.2.8.cpc.md"
        info = cpc.full_verify(str(capsule))
        self.assertTrue(cpc.full_profile_pass(info))
        self.assertEqual(info["state"]["project_name"], "PortAtlas")
        self.assertEqual(info["state"]["project_version"], "1.2.8")
        self.assertIn("Project/keep.txt", info["manifest"])
        self.assertNotIn("Project/omit.secret", info["manifest"])
        self.assertFalse(any(cpc.compare(str(capsule), self.source)[:3]))
        receipt = json.loads(Path(result["validation"]).read_text())
        self.assertEqual(receipt["capsule_sha256"], hashlib.sha256(capsule.read_bytes()).hexdigest())
        self.assertEqual(info["carrier_sha256"], receipt["capsule_sha256"])
        self.assertEqual(receipt["content_id"], info["content_id"])
        self.assertEqual(receipt["checks"]["clean_restore_comparison"], "equal")
        self.assertEqual(receipt["project_validation"], "not_run")
        self.assertTrue(receipt["created_at_utc"].endswith("Z"))
        self.assertIn("Project/omit.secret", receipt["selection"]["excluded_paths"])
        self.assertEqual((self.source / "main.txt").read_bytes(), b"original\n")
        self.assertEqual(list(self.root.glob(".cpc-handoff-*")), [])

    def test_selection_survives_restore_repack_compare_and_export(self):
        baseline = self.root / "original.cpc.md"
        cpc.pack(str(self.source), str(baseline), includes=["keep.txt"], excludes=["*.secret"])
        restored, _, _ = cpc.unpack(str(baseline), str(self.root / "restore"), keep_state=True)
        restored = Path(restored)
        (restored / "keep.txt").write_bytes(b"edited included file\n")
        (restored / "later.secret").write_bytes(b"new excluded file\n")
        repacked = self.root / "repacked.cpc.md"
        cpc.repack(str(restored), str(repacked))
        self.assertFalse(any(cpc.compare(str(repacked), restored)[:3]))
        manifest = cpc.full_verify(str(repacked))["manifest"]
        self.assertIn("original/keep.txt", manifest)
        self.assertNotIn("original/later.secret", manifest)
        cpc.export_project(str(restored), str(self.root / "export"))
        exported = next((self.root / "export").glob("*.cpc.md"))
        self.assertFalse(any(cpc.compare(str(exported), restored)[:3]))

    def test_cold_sandbox_edits_and_returns_using_only_exported_tool(self):
        (self.source / "data.bin").write_bytes(random.Random(3).randbytes(180000))
        for limit in (25_000_000, 131072):
            with self.subTest(limit=limit):
                cold = self.root / str(limit)
                cold.mkdir()
                attachments = cold / "attachments"
                first = cpc.handoff(self.source, attachments, "PortAtlas", "1.2.8", limit,
                                    includes=["keep.txt"], excludes=["*.secret"])
                guide = (attachments / "HANDOFF.md").read_text(encoding="utf-8")
                receiver = guide.split("````python\n", 1)[1].rsplit("````", 1)[0]
                self.assertEqual(receiver, (ROOT / "bin/cpc.py").read_text(encoding="utf-8").rstrip("\n") + "\n")
                (cold / "cpc-recover.py").write_text(receiver, encoding="utf-8")

                def run(*args):
                    p = subprocess.run([sys.executable, "-I", "cpc-recover.py", *args],
                                       cwd=cold, capture_output=True, text=True, timeout=30)
                    self.assertEqual(p.returncode, 0, p.stderr)
                    return p

                if first["split"]:
                    run("join", "./attachments", "-o", "./input.cpc.md")
                else:
                    shutil.copyfile(attachments / "PortAtlas-1.2.8.cpc.md", cold / "input.cpc.md")
                self.assertIn("--expect-sha256 " + first["set_sha256"], guide)
                run("v", "./input.cpc.md", "--strict", "--expect-sha256", first["set_sha256"])
                run("u", "./input.cpc.md", "-o", "./recovered", "--strict", "--state",
                    "--expect-sha256", first["set_sha256"])
                tree = cold / "recovered/input"
                (tree / "main.txt").write_bytes(b"edited in cold sandbox\n")
                (tree / "later.secret").write_bytes(b"must remain excluded\n")
                returned = run("handoff", "./recovered/input", "-o", "./return-files",
                               "--project-name", "PortAtlas", "--project-version", "1.2.9",
                               "--max-file-size", str(limit))
                self.assertIn("CPC HANDOFF PASS", returned.stdout)
                report = json.loads((cold / "return-files/VALIDATION.json").read_text())
                self.assertEqual(report["project_version"], "1.2.9")
                if first["split"]:
                    run("join", "./return-files", "-o", "./returned.cpc.md")
                else:
                    shutil.copyfile(cold / "return-files/PortAtlas-1.2.9.cpc.md", cold / "returned.cpc.md")
                run("v", "./returned.cpc.md", "--strict", "--expect-sha256", report["capsule_sha256"])
                self.assertIn("CPC EQUAL", run("c", "./returned.cpc.md", "./recovered/input").stdout)
                run("u", "./returned.cpc.md", "-o", "./next", "--strict", "--state")
                next_tree = cold / "next/returned"
                self.assertEqual((next_tree / "main.txt").read_bytes(), b"edited in cold sandbox\n")
                self.assertEqual((next_tree / "keep.txt").read_bytes(), b"explicit include\n")
                self.assertFalse((next_tree / "later.secret").exists())
                self.assertTrue((next_tree / "empty").is_dir())
                self.assertTrue(all(p.stat().st_size <= limit for p in (cold / "return-files").iterdir()))

    def test_unreadable_source_directory_fails_instead_of_disappearing(self):
        restricted = self.source / "restricted"
        restricted.mkdir()
        (restricted / "important.txt").write_bytes(b"must not silently disappear\n")
        original_scandir = os.scandir

        def deny_restricted(path):
            # shutil may scan directory descriptors while cleaning up.
            if not isinstance(path, int) and os.path.abspath(os.fspath(path)) == str(restricted):
                raise PermissionError(errno.EACCES, "injected unreadable directory", str(restricted))
            return original_scandir(path)

        with patch.object(os, "scandir", side_effect=deny_restricted):
            output = self.root / "failed-scan"
            with self.assertRaisesRegex(cpc.CPCError, "SOURCE_READ_FAILED"):
                cpc.handoff(self.source, output)
            self.assertFalse(output.exists())
            self.assertEqual(list(self.root.glob(".cpc-handoff-*")), [])
            # An explicit exclusion is a recorded policy choice, not an I/O failure.
            result = cpc.handoff(self.source, self.root / "excluded", excludes=["restricted"])
        report = json.loads(Path(result["validation"]).read_text())
        self.assertIn("Project/restricted", report["selection"]["excluded_paths"])

    def test_expected_identity_rejects_a_different_valid_capsule_before_decompression(self):
        first = self.root / "first.cpc.md"
        second = self.root / "second.cpc.md"
        cpc.pack(str(self.source), str(first))
        expected = hashlib.sha256(first.read_bytes()).hexdigest()
        (self.source / "main.txt").write_bytes(b"another valid snapshot\n")
        cpc.pack(str(self.source), str(second))
        self.assertTrue(cpc.full_profile_pass(cpc.full_verify(str(second))))
        info = cpc.full_verify(str(first), expected_sha256=expected.upper())
        self.assertEqual(info["carrier_sha256"], expected)
        with patch.object(cpc, "decompress_to_file", side_effect=AssertionError("must reject before decompression")):
            with self.assertRaisesRegex(cpc.CPCError, "CAPSULE_HASH_MISMATCH"):
                cpc.full_verify(str(second), expected_sha256=expected)
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(cpc.main(["v", str(second), "--strict", "--expect-sha256", expected]), 2)
            self.assertEqual(cpc.main(["u", str(second), "-o", str(self.root / "wrong"),
                                      "--strict", "--expect-sha256", expected]), 2)
            self.assertEqual(cpc.main([str(second), "-o", str(self.root / "implicit-wrong"),
                                      "--expect-sha256", expected]), 2)
            self.assertEqual(cpc.main(["v", str(first), "--expect-sha256", "not-a-hash"]), 2)
            self.assertEqual(cpc.main(["p", str(self.source), "--expect-sha256", expected]), 2)
        self.assertFalse((self.root / "wrong").exists())
        self.assertFalse((self.root / "implicit-wrong").exists())

    def test_failed_verification_comparison_or_export_never_publishes(self):
        cases = (
            ("full_verify", {"side_effect": cpc.CPCError("INVALID_HEADER")}),
            ("compare", {"return_value": (["unexpected"], [], [], [])}),
            ("export_capsule", {"side_effect": OSError("simulated disk full")}),
        )
        for function, settings in cases:
            with self.subTest(function=function), patch.object(cpc, function, **settings):
                out = self.root / function
                with self.assertRaises((cpc.CPCError, OSError)):
                    cpc.handoff(self.source, out)
                self.assertFalse(out.exists())
                self.assertEqual(list(self.root.glob(".cpc-handoff-*")), [])

    def test_bad_names_versions_and_output_are_rejected(self):
        for name in ("../elsewhere", "a/b", "CON", "bad:name"):
            with self.subTest(name=name), self.assertRaises(cpc.CPCError):
                cpc.handoff(self.source, self.root / "invalid", name)
        for version in ("1.2", "1.2.03", "1.2.-1", "1.2.3-rc.1"):
            with self.subTest(version=version), self.assertRaisesRegex(cpc.CPCError, "PROJECT_VERSION"):
                cpc.handoff(self.source, self.root / "invalid", "Project", version)
        with self.assertRaisesRegex(cpc.CPCError, "EXPORT_INSIDE_SOURCE"):
            cpc.handoff(self.source, self.source / "return")
        existing = self.root / "existing"
        existing.mkdir()
        (existing / "sentinel").write_bytes(b"keep")
        with self.assertRaisesRegex(cpc.CPCError, "DEST_EXISTS"):
            cpc.handoff(self.source, existing)
        self.assertEqual((existing / "sentinel").read_bytes(), b"keep")
        with self.assertRaisesRegex(cpc.CPCError, "HANDOFF_LIMIT"):
            cpc.handoff(self.source, self.root / "small", limit=4096)
        self.assertFalse((self.root / "small").exists())

    def test_cli_labels_are_scoped_and_tool_version_remains_available(self):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(cpc.main(["handoff", str(self.source), "-o", str(self.root / "cli"),
                                       "--project-name", "PortAtlas", "--project-version", "1.2.8"]), 0)
            self.assertEqual(cpc.main(["p", str(self.source), "--project-version", "1.2.8"]), 2)
            self.assertEqual(cpc.main(["handoff", str(self.source), "-f"]), 2)
        p = subprocess.run([sys.executable, str(ROOT / "bin/cpc.py"), "--version"],
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn(cpc.RELEASE_VERSION, p.stdout)


if __name__ == "__main__":
    unittest.main()
