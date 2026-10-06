#!/usr/bin/env python3
# Copyright 2026 RioPlay
# SPDX-License-Identifier: MIT
import base64
import hashlib
import importlib.util
import io
import lzma
import os
from pathlib import Path
import tempfile
import tarfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("cpc", ROOT / "bin/cpc.py")
cpc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cpc)


class StreamingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="cpc-stream-test-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "Project"
        self.source.mkdir()
        (self.source / "main.py").write_bytes(b"print('hello')\r\n")
        (self.source / "empty").mkdir()
        self.cap = self.root / "Project.cpc.md"

    def test_same_bytes_as_buffered_encoding(self):
        for preset in (6, 9, 9 | lzma.PRESET_EXTREME):
            cpc.pack(str(self.source), str(self.cap), force=True, preset=preset)
            with cpc.parse_capsule(str(self.cap)) as info:
                raw = info["raw"].read()
            packed = lzma.compress(raw, format=lzma.FORMAT_XZ, preset=preset)
            expected = (f"#CPC|1|b64>xz>tar|{hashlib.sha256(packed).hexdigest()}\n<CPC>\n"
                        + base64.b64encode(packed).decode() + "\n</CPC>\n").encode()
            self.assertEqual(self.cap.read_bytes(), expected)

    def test_chunk_boundaries_and_whitespace(self):
        cpc.pack(str(self.source), str(self.cap), preset=6)
        canonical = self.cap.read_bytes()
        lines = canonical.splitlines()
        wrapped = b"\r\n".join([lines[0], lines[1],
                                b" \t\r\n".join(lines[2][i:i+13] for i in range(0, len(lines[2]), 13)),
                                lines[3]]) + b"\r\n"
        expected = cpc.full_verify(str(self.cap))["content_id"]
        for content in (canonical, wrapped):
            self.cap.write_bytes(content)
            for chunk_size in (1, 2, 3, 5, 7, 31, 1024):
                with self.subTest(chunk_size=chunk_size), patch.object(cpc, "IO_CHUNK", chunk_size):
                    self.assertEqual(cpc.full_verify(str(self.cap))["content_id"], expected)

    def test_reject_malformed_across_chunk_boundaries(self):
        cpc.pack(str(self.source), str(self.cap), preset=6)
        data = self.cap.read_bytes()
        mutations = (
            data.replace(b"<CPC>", b"</CPC>"),
            data + b"<CPC>AA==</CPC>",
            data.replace(b"</CPC>", b""),
            data.replace(b"\n</CPC>", b"!\n</CPC>"),
            data.replace(b"\n</CPC>", b"AAAA\n</CPC>"),
        )
        for content in mutations:
            self.cap.write_bytes(content)
            with patch.object(cpc, "IO_CHUNK", 7):
                with self.assertRaises(cpc.CPCError):
                    cpc.full_verify(str(self.cap))
        # Padding must end the Base64 stream, even at a chunk boundary.
        payload = b"a"
        header = f"#CPC|1|b64>xz>tar|{hashlib.sha256(payload).hexdigest()}\n<CPC>\n".encode()
        with patch.object(cpc, "IO_CHUNK", 4):
            with self.assertRaisesRegex(cpc.CPCError, "BAD_BASE64"):
                cpc.decode_carrier(io.BytesIO(header + b"YQ==AAAA\n</CPC>\n"), io.BytesIO())

    def test_temporary_files_closed_on_success_and_failure(self):
        cpc.pack(str(self.source), str(self.cap), preset=6)
        original = cpc.tempfile.TemporaryFile
        handles = []
        def track(*args, **kwargs):
            handle = original(*args, **kwargs)
            handles.append(handle)
            return handle
        with patch.object(cpc.tempfile, "TemporaryFile", side_effect=track):
            cpc.full_verify(str(self.cap))
            self.cap.write_bytes(self.cap.read_bytes().replace(b"<CPC>", b"<BAD>"))
            with self.assertRaises(cpc.CPCError):
                cpc.full_verify(str(self.cap))
        self.assertTrue(handles)
        self.assertTrue(all(handle.closed for handle in handles))

    def test_failed_pack_preserves_destination_and_cleans_stage(self):
        self.cap.write_bytes(b"original")
        with patch.object(cpc, "full_verify", side_effect=cpc.CPCError("injected verification failure")):
            with self.assertRaises(cpc.CPCError):
                cpc.pack(str(self.source), str(self.cap), force=True, preset=6)
        self.assertEqual(self.cap.read_bytes(), b"original")
        self.assertFalse(list(self.root.glob(".cpc-*.tmp")))

    def test_failed_unpack_preserves_destination(self):
        cpc.pack(str(self.source), str(self.cap), preset=6)
        out = self.root / "out"
        old = out / "Project"
        old.mkdir(parents=True)
        (old / "keep.txt").write_bytes(b"original")
        with patch.object(cpc.shutil, "copyfileobj", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                cpc.unpack(str(self.cap), str(out), force=True)
        self.assertEqual((old / "keep.txt").read_bytes(), b"original")
        self.assertFalse(list(out.glob(".cpc-stage-*")))
        cpc.unpack(str(self.cap), str(out), backup=True)
        self.assertEqual((out / "Project.bak/keep.txt").read_bytes(), b"original")
        self.assertEqual((old / "main.py").read_bytes(), b"print('hello')\r\n")

    def test_metadata_read_guard(self):
        header = tarfile.TarInfo("extended-header")
        header.type = tarfile.XHDTYPE
        header.size = 2048
        with patch.object(cpc, "MAX_METADATA", 1024):
            with self.assertRaisesRegex(cpc.CPCError, "METADATA_LIMIT"):
                cpc.validate_archive(header.tobuf() + b"\0" * 2048)

    def test_publish_failure_restores_previous_directory(self):
        staged = self.root / "staged"
        staged.mkdir()
        (staged / "new.txt").write_bytes(b"new")
        original = cpc.os.replace
        def fail_publish(source, target):
            if Path(source) == staged:
                raise OSError("injected rename failure")
            return original(source, target)
        with patch.object(cpc.os, "replace", side_effect=fail_publish):
            with self.assertRaises(OSError):
                cpc.publish_extraction(str(staged), str(self.source), True, False)
        self.assertEqual((self.source / "main.py").read_bytes(), b"print('hello')\r\n")
        self.assertFalse(list(self.root.glob(".cpc-old-*")))

    def test_report_counts_only_selected_files(self):
        (self.source / "ignored.bin").write_bytes(b"x" * 4096)
        result = cpc.pack(str(self.source), str(self.cap), preset=6, excludes=["ignored.bin"])
        self.assertEqual(result["source_bytes"], len(b"print('hello')\r\n"))
        self.assertEqual(result["largest_files"], [("Project/main.py", result["source_bytes"])])

    def test_executable_intent_survives_repack_and_edits(self):
        (self.source / "run.sh").write_bytes(b"#!/bin/sh\necho original\n")
        (self.source / "data.exe").write_bytes(b"not executable")
        cpc.pack(str(self.source), str(self.cap), preset=6,
                 file_exec={"run.sh": True, "data.exe": False})
        before = cpc.full_verify(str(self.cap))
        restored, side, _ = cpc.unpack(str(self.cap), str(self.root / "out"))
        restored = Path(restored)
        _, state = cpc.read_sidecar_for(str(restored))
        intent = cpc.recorded_executable_intent(state)
        self.assertIs(intent["run.sh"], True)
        self.assertIs(intent["data.exe"], False)
        self.assertEqual(cpc.compare(str(self.cap), str(restored))[:3], ([], [], []))
        unchanged = self.root / "unchanged.cpc.md"
        result = cpc.repack(str(restored), str(unchanged), preset=6)
        self.assertEqual(result["content_id"], before["content_id"])

        (restored / "run.sh").write_bytes(b"#!/bin/sh\necho edited\n")
        (restored / "new.txt").write_bytes(b"new")
        (restored / "main.py").unlink()
        changed = self.root / "edited.cpc.md"
        cpc.repack(str(restored), str(changed), preset=6)
        manifest = cpc.full_verify(str(changed))["manifest"]
        self.assertTrue(manifest["Project/run.sh"][2])
        self.assertFalse(manifest["Project/data.exe"][2])
        self.assertFalse(manifest["Project/new.txt"][2])
        self.assertNotIn("Project/main.py", manifest)

    def test_single_file_executable_intent(self):
        script = self.root / "run.sh"
        script.write_bytes(b"#!/bin/sh\necho hello\n")
        cpc.pack(str(script), str(self.cap), preset=6, file_exec={".": True})
        restored, _, original = cpc.unpack(str(self.cap), str(self.root / "out"))
        result = cpc.repack(restored, str(self.root / "returned.cpc.md"), preset=6)
        self.assertEqual(result["content_id"], original["content_id"])

    @unittest.skipIf(os.name == "nt", "Unix chmod semantics require a POSIX filesystem")
    def test_posix_chmod_overrides_recorded_intent(self):
        (self.source / "run.sh").write_bytes(b"#!/bin/sh\necho hello\n")
        cpc.pack(str(self.source), str(self.cap), preset=6, file_exec={"run.sh": True})
        restored, _, _ = cpc.unpack(str(self.cap), str(self.root / "out"))
        (Path(restored) / "run.sh").chmod(0o644)
        (Path(restored) / "main.py").chmod(0o755)
        changed = self.root / "chmod.cpc.md"
        cpc.repack(restored, str(changed), preset=6)
        manifest = cpc.full_verify(str(changed))["manifest"]
        self.assertFalse(manifest["Project/run.sh"][2])
        self.assertTrue(manifest["Project/main.py"][2])
        self.assertEqual(set(cpc.compare(str(self.cap), restored)[2]),
                         {"Project/run.sh", "Project/main.py"})

    def test_old_sidecar_without_executable_map_still_works(self):
        cpc.pack(str(self.source), str(self.cap), preset=6)
        restored, side, _ = cpc.unpack(str(self.cap), str(self.root / "out"))
        p = Path(side)
        p.write_text("\n".join(line for line in p.read_text().splitlines()
                              if not line.startswith("file_exec=")) + "\n")
        cpc.repack(restored, str(self.root / "legacy.cpc.md"), preset=6)

    def test_executable_metadata_validation(self):
        for value in ('[]', '{"run.sh": 1}', '{"run.sh": "false"}', '{"../run.sh": true}'):
            with self.subTest(value=value), self.assertRaises(cpc.CPCError):
                cpc.recorded_executable_intent({"file_exec": value})
        cpc.pack(str(self.source), str(self.cap), preset=6)
        raw = io.BytesIO()
        with cpc.parse_capsule(str(self.cap)) as info:
            with cpc.open_tar(info["raw"]) as source, tarfile.open(fileobj=raw, mode="w") as target:
                for member in source:
                    data = source.extractfile(member) if member.isfile() else None
                    if member.name == "Project/main.py":
                        member.mode ^= 0o111
                    target.addfile(member, data)
        with self.assertRaisesRegex(cpc.CPCError, "MANIFEST_MISMATCH"):
            cpc.validate_archive(raw.getvalue())


if __name__ == "__main__":
    unittest.main()
