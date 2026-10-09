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
                    cpc.unpack(str(self.path), output=str(destination), force=True, strict=True)
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

    def extension(self, size, kind=tarfile.XHDTYPE):
        header = tarfile.TarInfo("extension")
        header.type = kind
        header.size = size
        if size:
            if kind in (tarfile.GNUTYPE_LONGNAME, tarfile.GNUTYPE_LONGLINK):
                data = b"x" * (size - 1) + b"\0"
            else:
                prefix = str(size).encode() + b" comment="
                data = prefix + b"x" * (size - len(prefix) - 1) + b"\n"
        else:
            data = b""
        return header.tobuf() + data + b"\0" * (-size % 512)

    def test_windows_nonportable_names_rejected_during_archive_validation(self):
        names = [f"demo_project/control{chr(value)}.txt" for value in range(1, 32)]
        names += [f"demo_project/{prefix}{digit}{suffix}"
                  for prefix in ("COM", "LPT") for digit in "¹²³"
                  for suffix in ("", ".txt", "/child.txt")]
        for name in names:
            with self.subTest(name=repr(name)):
                member = tarfile.TarInfo(name)
                with self.assertRaisesRegex(cpc.CPCError, "NONPORTABLE_NAME"):
                    cpc.validate_archive(self.altered_tar(extra=[member]))
        for name in ("demo_project/control\x01.txt", "demo_project/COM¹", "demo_project/LPT³.txt"):
            self.carrier(lzma.compress(self.altered_tar(extra=[tarfile.TarInfo(name)])))
            with patch.object(cpc, "extract_members") as extract:
                for strict in (False, True):
                    with self.assertRaisesRegex(cpc.CPCError, "NONPORTABLE_NAME"):
                        cpc.unpack(str(self.path), str(Path(self.tmp.name)/"out"), strict=strict)
                with self.assertRaisesRegex(cpc.CPCError, "NONPORTABLE_NAME"):
                    cpc.recover(str(self.path), str(Path(self.tmp.name)/"recovery"))
                extract.assert_not_called()
        # Ordinary Unicode and device-name prefixes are valid filenames.
        for name in ("demo_project/café.txt", "demo_project/COM¹-report.txt", "demo_project/LPT³notes"):
            cpc.portable_name_check(name)

    def assert_rejected_before_extraction(self, raw, error):
        self.carrier(lzma.compress(raw, preset=0))
        with patch.object(cpc, "unpack_verified") as extract:
            with self.assertRaisesRegex(cpc.CPCError, error):
                cpc.unpack(str(self.path), str(Path(self.tmp.name)/"out"), strict=True)
            extract.assert_not_called()

    def test_extension_limit_before_body_allocation(self):
        for kind in (tarfile.XHDTYPE, tarfile.XGLTYPE, tarfile.SOLARIS_XHDTYPE,
                     tarfile.GNUTYPE_LONGNAME, tarfile.GNUTYPE_LONGLINK):
            header = tarfile.TarInfo("extension")
            header.type = kind
            header.size = cpc.MAX_EXTENSION + 1
            # No body exists: the declared-size error must precede any body read.
            self.assert_rejected_before_extraction(header.tobuf(), "EXTENSION_LIMIT")
        self.carrier(lzma.compress(self.extension(cpc.MAX_EXTENSION)+self.raw, preset=0))
        self.assertEqual(cpc.full_verify(str(self.path))["content_id"],
                         cpc.full_verify(str(ROOT/"demo_project.cpc.md"))["content_id"])

    def test_cumulative_extensions_and_internal_metadata(self):
        # Individually permitted PAX records must also share one cumulative budget.
        with patch.object(cpc, "MAX_METADATA", 32 * 1024):
            self.assert_rejected_before_extraction(
                self.extension(16 * 1024)*3+self.raw, "METADATA_LIMIT")
        with tarfile.open(fileobj=io.BytesIO(self.raw), mode="r:") as archive:
            internal = sum(m.size for m in archive if m.name.startswith('.cpc/') and m.isfile())
        with patch.object(cpc, "MAX_METADATA", internal):
            cpc.validate_archive(self.raw)
            self.assert_rejected_before_extraction(self.extension(512)+self.raw, "METADATA_LIMIT")
        with patch.object(cpc, "MAX_METADATA", internal-1):
            self.assert_rejected_before_extraction(self.raw, "METADATA_LIMIT")

    def test_hidden_headers_count_and_recursion_limit(self):
        with patch.object(cpc, "MAX_MEMBERS", 3):
            self.assert_rejected_before_extraction(self.extension(0)*4+self.raw, "MEMBER_LIMIT")
        self.assert_rejected_before_extraction(
            self.extension(0)*(cpc.MAX_EXTENSION_DEPTH+1)+self.raw, "EXTENSION_DEPTH_LIMIT")
        with patch.object(cpc, "MAX_MEMBERS", 20):
            raw = b"".join(tarfile.TarInfo("file"+str(i)).tobuf() for i in range(21))
            self.assert_rejected_before_extraction(raw, "MEMBER_LIMIT")

    def test_pax_cannot_enable_sparse_decoding(self):
        for attributes in (
            {'GNU.sparse.size': '0'},
            {'GNU.sparse.map': '0,0'},
            {'GNU.sparse.major': '1', 'GNU.sparse.minor': '0',
             'GNU.sparse.realsize': '0', 'GNU.sparse.name': 'file'},
        ):
            raw = io.BytesIO()
            with tarfile.open(fileobj=raw, mode='w', format=tarfile.PAX_FORMAT) as archive:
                member = tarfile.TarInfo('file')
                member.pax_headers = attributes
                archive.addfile(member, io.BytesIO())
            self.assert_rejected_before_extraction(raw.getvalue(), 'UNSUPPORTED_MEMBER_TYPE')


if __name__ == "__main__":
    unittest.main()
