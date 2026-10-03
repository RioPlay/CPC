#!/usr/bin/env python3
# Copyright 2026 RioPlay
# SPDX-License-Identifier: MIT
import base64
import hashlib
import importlib.util
import io
import lzma
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("cpc", ROOT / "bin/cpc.py")
cpc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cpc)


class ReceiverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="cpc-security-")
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "input.cpc.md"
        self.raw = self.parse(ROOT / "demo_project.cpc.md")["raw"]

    def parse(self, path):
        with cpc.parse_capsule(str(path)) as info:
            return dict(info, raw=info["raw"].read())

    def carrier(self, packed):
        digest = hashlib.sha256(packed).hexdigest()
        self.path.write_text(
            f"#CPC|1|b64>xz>tar|{digest}\n<CPC>\n"
            + base64.b64encode(packed).decode("ascii") + "\n</CPC>\n",
            encoding="utf-8")

    def test_expanded_boundary_and_bomb(self):
        self.carrier(lzma.compress(self.raw))
        with patch.object(cpc, "MAX_TAR", len(self.raw)):
            self.assertEqual(self.parse(self.path)["raw"], self.raw)
        with patch.object(cpc, "MAX_TAR", len(self.raw) - 1):
            with self.assertRaisesRegex(cpc.CPCError, "TAR_LIMIT"):
                self.parse(self.path)
        self.carrier(lzma.compress(b"x" * (1024 * 1024)))
        with patch.object(cpc, "MAX_TAR", 1024):
            with self.assertRaisesRegex(cpc.CPCError, "TAR_LIMIT"):
                self.parse(self.path)

    def test_decoder_memory_limit(self):
        self.carrier(lzma.compress(self.raw))
        with patch.object(cpc, "MAX_LZMA_MEMORY", 1024):
            with self.assertRaisesRegex(cpc.CPCError, "DECOMPRESSION_FAILED"):
                self.parse(self.path)

    def test_hash_checked_before_decoder(self):
        self.carrier(lzma.compress(self.raw))
        text = self.path.read_text()
        self.path.write_text(text.replace(text.splitlines()[0].split("|")[-1], "0" * 64))
        with patch.object(cpc.lzma, "LZMADecompressor") as decoder:
            with self.assertRaisesRegex(cpc.CPCError, "HASH_MISMATCH"):
                self.parse(self.path)
            decoder.assert_not_called()

    def test_reject_incomplete_extra_and_wrong_codec(self):
        packed = lzma.compress(self.raw)
        for payload in (packed[:-8], packed + b"junk", packed + packed,
                        lzma.compress(self.raw, format=lzma.FORMAT_ALONE)):
            with self.subTest(payload_bytes=len(payload)):
                self.carrier(payload)
                with self.assertRaisesRegex(cpc.CPCError, "DECOMPRESSION_FAILED"):
                    self.parse(self.path)

    def test_carrier_and_compressed_limits(self):
        packed = lzma.compress(self.raw)
        self.carrier(packed)
        for setting, ceiling, error in (
            ("MAX_CARRIER", self.path.stat().st_size - 1, "CARRIER_LIMIT"),
            ("MAX_COMPRESSED", len(packed) - 1, "COMPRESSED_LIMIT"),
        ):
            with patch.object(cpc, setting, ceiling):
                with self.assertRaisesRegex(cpc.CPCError, error):
                    self.parse(self.path)

    def test_member_limit(self):
        with patch.object(cpc, "MAX_MEMBERS", 1):
            with self.assertRaisesRegex(cpc.CPCError, "MEMBER_LIMIT"):
                cpc.validate_archive(self.raw)

    def altered_tar(self, extra=None, root=None):
        output = io.BytesIO()
        with tarfile.open(fileobj=io.BytesIO(self.raw), mode="r:") as source:
            with tarfile.open(fileobj=output, mode="w") as dest:
                for member in source:
                    data = source.extractfile(member).read() if member.isfile() else None
                    if root is not None and member.name == ".cpc/state":
                        data = ("v=1\nroot=" + root + "\ntype=dir\n").encode()
                        member.size = len(data)
                    dest.addfile(member, io.BytesIO(data) if data is not None else None)
                for member in extra or ():
                    dest.addfile(member)
        return output.getvalue()

    def test_unsafe_roots_never_publish(self):
        for root in ("../escape", "/absolute", "C:/escape", ".cpc", "other"):
            with self.subTest(root=root):
                self.carrier(lzma.compress(self.altered_tar(root=root)))
                destination = Path(self.tmp.name) / "out"
                with self.assertRaises(cpc.CPCError):
                    cpc.unpack(str(self.path), output=str(destination), force=True)
                self.assertFalse(destination.exists())

    def test_unsafe_members(self):
        for name, kind, error in (
            ("../escape", tarfile.REGTYPE, "UNSAFE_PATH"),
            ("/absolute", tarfile.REGTYPE, "UNSAFE_PATH"),
            ("demo_project/link", tarfile.SYMTYPE, "UNSUPPORTED_MEMBER_TYPE"),
            ("demo_project", tarfile.DIRTYPE, "DUPLICATE_MEMBER"),
            ("DEMO_PROJECT", tarfile.DIRTYPE, "CASE_COLLISION"),
        ):
            with self.subTest(name=name):
                member = tarfile.TarInfo(name)
                member.type = kind
                with self.assertRaisesRegex(cpc.CPCError, error):
                    cpc.validate_archive(self.altered_tar(extra=[member]))


if __name__ == "__main__":
    unittest.main()
