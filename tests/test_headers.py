#!/usr/bin/env python3
# Copyright 2026 RioPlay
# SPDX-License-Identifier: MIT
"""Payload-first restoration must report uncertainty, never guess unsafe data."""
import base64
from contextlib import redirect_stderr, redirect_stdout
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
spec = importlib.util.spec_from_file_location('cpc', ROOT/'bin/cpc.py')
cpc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cpc)


class HeaderTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='cpc-header-test-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.source = self.root/'Original'
        self.source.mkdir()
        (self.source/'empty').mkdir()
        (self.source/'result.txt').write_bytes(b'completed work\r\n')
        self.cap = self.root/'Returned.cpc.md'
        cpc.pack(str(self.source), str(self.cap))
        self.canonical = self.cap.read_bytes()
        self.header, rest = self.canonical.split(b'<CPC>', 1)
        self.body = rest.split(b'</CPC>', 1)[0]
        self.digest = self.header.strip().split(b'|')[-1]

    def cli(self, *args):
        with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
            code = cpc.main(list(map(str, args)))
        return code, out.getvalue(), err.getvalue()

    def carrier(self, prefix=b'', suffix=b''):
        return prefix+b'<CPC>'+self.body+b'</CPC>'+suffix

    def test_advisory_headers_restore_exact_contents_and_return_valid_capsule(self):
        variants = [
            (b'', 'unverified'),
            (b'not a recognized header\n', 'unverified'),
            (b'CPC|1|tar.xz+base64|'+self.digest+b'|1245864|WRONG_PROJECT_NAME\n', 'verified'),
            (b'#CPC|1|b64>xz>tar|'+b'0'*64+b'\n', 'mismatch'),
            (b'#CPC|9|invented-codec|bad-hash|size=unknown\n', 'unverified'),
        ]
        for index, (prefix, integrity) in enumerate(variants):
            with self.subTest(integrity=integrity, prefix=prefix):
                self.cap.write_bytes(self.carrier(prefix))
                parent = self.root/f'case-{index}'
                code, out, err = self.cli(self.cap, '-o', parent)
                self.assertEqual(code, 0, err)
                self.assertIn('CPC WARNING', err)
                if integrity != 'verified':
                    self.assertIn('RESTORED integrity='+integrity, out)
                    self.assertNotIn('CPC PASS', out)
                tree = parent/'Returned'
                self.assertEqual((tree/'result.txt').read_bytes(), b'completed work\r\n')
                self.assertTrue((tree/'empty').is_dir())
                self.assertFalse((parent/'WRONG_PROJECT_NAME').exists())
                returned = self.root/f'new-{index}.cpc.md'
                self.assertEqual(self.cli('r', tree, '-o', returned)[0], 0)
                code, out, err = self.cli('v', returned, '--strict')
                self.assertEqual(code, 0, err)
                self.assertIn('integrity=verified', out)
                self.assertFalse(Path(str(self.cap)+'.cpc.md').exists())

    def test_presentation_wrappers_and_generic_markdown_autodetection(self):
        variants = [b'\xef\xbb\xbf'+self.canonical,
                    self.carrier(b'# Returned project\n```text\n', b'\n```\nDone.'),
                    self.carrier(b'\n\n'+self.header, b'\nnotes after the capsule')]
        for index, data in enumerate(variants):
            capsule = self.root/f'attachment-{index}.md'
            capsule.write_bytes(data)
            self.assertTrue(cpc.is_capsule(str(capsule)))
            code, _, err = self.cli(capsule, '-o', self.root/f'wrapped-{index}')
            self.assertEqual(code, 0, err)
        ordinary = self.root/'ordinary.md'
        ordinary.write_text('Example: <CPC>BASE64</CPC>\n', encoding='utf-8')
        self.assertFalse(cpc.is_capsule(str(ordinary)))

    def test_quiet_verification_reports_integrity_and_never_silences_warning(self):
        self.cap.write_bytes(self.carrier())
        code, out, err = self.cli('v', self.cap)
        self.assertEqual(code, 0, err)
        self.assertIn('CPC RESTORABLE', out)
        self.assertIn('integrity=unverified', out)
        code, out, err = self.cli('v', self.cap, '-q')
        self.assertEqual(code, 0)
        self.assertEqual(out, '')
        self.assertIn('sender integrity is unverified', err)

    def test_strict_still_requires_canonical_header_and_matching_hash_before_xz(self):
        for data, error in [(self.carrier(), 'INVALID_METADATA'),
                            (self.carrier(b'#CPC|1|b64>xz>tar|'+b'0'*64+b'\n'), 'HASH_MISMATCH')]:
            self.cap.write_bytes(data)
            with patch.object(cpc, 'decompress_to_file') as decoder:
                code, _, err = self.cli('u', self.cap, '-o', self.root/'strict', '--strict')
            self.assertEqual(code, 2)
            self.assertIn(error, err)
            decoder.assert_not_called()
            self.assertFalse((self.root/'strict').exists())

    def test_streaming_boundaries_and_ambiguous_hashes(self):
        prefix = b'CPC|1|tar.xz+base64|'+self.digest+b'|123|Original\n'
        self.cap.write_bytes(self.carrier(prefix, b'\n```\n'))
        for size in range(1, 18):
            with patch.object(cpc, 'IO_CHUNK', size), cpc.parse_capsule(str(self.cap)) as info:
                self.assertEqual(info['integrity'], 'verified')
                self.assertEqual(info['capsule_hash'], self.digest.decode())
        self.cap.write_bytes(self.carrier(prefix+b'other hash: '+b'1'*64+b'\n'))
        with cpc.parse_capsule(str(self.cap)) as info:
            self.assertEqual(info['integrity'], 'unverified')
            self.assertIsNone(info['claimed_hash'])

    def test_marker_failures_never_repack_or_replace_project(self):
        tree = self.root/'out/Returned'
        tree.mkdir(parents=True)
        (tree/'keep').write_bytes(b'old project')
        for data in (b'not a capsule', b'<CPC>'+self.body,
                     self.carrier()+self.carrier(), b'<CPC>!!!!</CPC>'):
            self.cap.write_bytes(data)
            with patch.object(cpc, 'extract_members') as extract:
                code, _, err = self.cli(self.cap, '-o', tree.parent, '-f')
            self.assertEqual(code, 2, err)
            extract.assert_not_called()
            self.assertEqual((tree/'keep').read_bytes(), b'old project')
            self.assertFalse(Path(str(self.cap)+'.cpc.md').exists())

    def test_unverified_payload_safety_and_completeness_remain_mandatory(self):
        raw = io.BytesIO()
        with tarfile.open(fileobj=raw, mode='w') as archive:
            archive.addfile(tarfile.TarInfo('../escape'))
        valid_xz = base64.b64decode(b''.join(self.body.split()))
        for packed in (b'not xz', valid_xz[:-8], valid_xz*2, lzma.compress(raw.getvalue())):
            self.cap.write_bytes(b'<CPC>'+base64.b64encode(packed)+b'</CPC>')
            with patch.object(cpc, 'extract_members') as extract:
                code, _, _ = self.cli(self.cap, '-o', self.root/'unsafe')
            self.assertEqual(code, 2)
            extract.assert_not_called()
            self.assertFalse((self.root/'unsafe').exists())

    def test_preamble_and_epilogue_have_exact_bounded_limits(self):
        for data in (self.carrier(b'x'*17), self.carrier(suffix=b'x'*17)):
            with patch.object(cpc, 'MAX_METADATA', 16), patch.object(cpc, 'IO_CHUNK', 1):
                with self.assertRaisesRegex(cpc.CPCError, 'METADATA_LIMIT'):
                    cpc.decode_carrier(io.BytesIO(data), io.BytesIO())
        with patch.object(cpc, 'MAX_METADATA', 16), patch.object(cpc, 'IO_CHUNK', 1):
            cpc.decode_carrier(io.BytesIO(self.carrier(b'x'*16, b'x'*16)), io.BytesIO())

    def test_evidence_recovery_never_claims_a_missing_header_was_verified(self):
        self.cap.write_bytes(self.carrier())
        with redirect_stderr(io.StringIO()) as err:
            result = cpc.recover(str(self.cap), str(self.root/'evidence'))
        self.assertFalse(result['original_cpc_valid'])
        self.assertFalse(result['outer_hash_verified'])
        self.assertEqual(result['integrity'], 'unverified')
        self.assertIn('sender integrity is unverified', err.getvalue())
        self.assertEqual((self.root/'evidence/files/Original/result.txt').read_bytes(),
                         b'completed work\r\n')


if __name__ == '__main__':
    unittest.main()
