#!/usr/bin/env python3
# Copyright 2026 RioPlay
# SPDX-License-Identifier: MIT
"""Recovery accepts defective CPC metadata, never a defective safety boundary."""
import base64
from contextlib import redirect_stdout, redirect_stderr
import hashlib
import importlib.util
import io
import json
import lzma
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('cpc', ROOT/'bin/cpc.py')
cpc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cpc)
STAMP = 1735689600123456700


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='cpc-recovery-test-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.cap = self.root/'returned.cpc.md'
        self.output = self.root/'salvaged'

    def carrier(self, raw=None, packed=None):
        if packed is None:
            packed = lzma.compress(raw, preset=6)
        self.cap.write_bytes(('#CPC|1|b64>xz>tar|'+hashlib.sha256(packed).hexdigest()
                              +'\n<CPC>\n').encode()+base64.b64encode(packed)+b'\n</CPC>\n')

    def archive(self, entries):
        raw = io.BytesIO()
        with tarfile.open(fileobj=raw, mode='w', format=tarfile.PAX_FORMAT) as tf:
            for name, data in entries:
                m = name if isinstance(name, tarfile.TarInfo) else tarfile.TarInfo(name)
                if data is None:
                    if m.type == tarfile.REGTYPE:
                        m.type = tarfile.DIRTYPE
                else:
                    m.size = len(data)
                cpc.set_member_mtime(m, STAMP)
                tf.addfile(m, None if data is None else io.BytesIO(data))
        self.carrier(raw.getvalue())
        return raw.getvalue()

    def cli(self, *args):
        with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
            code = cpc.main(list(map(str, args)))
        return code, out.getvalue(), err.getvalue()

    def recover(self, **kwargs):
        return cpc.recover(str(self.cap), str(self.output), **kwargs)

    def assert_rejected(self, error):
        with self.assertRaisesRegex((cpc.CPCError, tarfile.TarError), error):
            self.recover()
        self.assertFalse(self.output.exists())
        self.assertFalse(list(self.root.glob('.cpc-stage-*')))

    def test_missing_metadata_parents_multiple_roots_and_roundtrip(self):
        executable = tarfile.TarInfo('Project/bin/run.sh')
        executable.mode = 0o755
        self.archive([('Project/src/caf\u00e9.txt', b'content\r\n'),
                      (executable, b'#!/bin/sh\necho ok\n'),
                      ('other/readme.md', b'other'), ('empty', None)])
        before = self.cap.read_bytes()
        code, out, err = self.cli('u', self.cap, '-o', self.root/'strict', '--strict')
        self.assertEqual(code, 2)
        self.assertIn('cpc recover', err)
        self.assertFalse((self.root/'strict').exists())
        result = self.recover()
        self.assertFalse(result['original_cpc_valid'])
        self.assertEqual(result['files'], 3)
        files = self.output/'files'
        self.assertEqual((files/'Project/src/caf\u00e9.txt').read_bytes(), b'content\r\n')
        self.assertEqual((files/'Project/src/caf\u00e9.txt').stat().st_mtime_ns, STAMP)
        self.assertTrue((files/'empty').is_dir())
        self.assertEqual((files/'empty').stat().st_mtime_ns, STAMP)
        self.assertEqual(self.cap.read_bytes(), before)
        state = cpc.read_sidecar_for(str(files))[1]
        self.assertEqual(state['profile'], 'archive')
        self.assertEqual(json.loads(state['file_exec'])['Project/bin/run.sh'], True)
        cap = self.root/'repaired.cpc.md'
        cpc.repack(str(files), str(cap))
        info = cpc.full_verify(str(cap))
        self.assertTrue(info['manifest']['files/Project/bin/run.sh'][2])
        out, _, _ = cpc.unpack(str(cap), str(self.root/'next'))
        self.assertEqual((Path(out)/'other/readme.md').read_bytes(), b'other')
        self.assertFalse((Path(out)/'recovery.json').exists())
        self.assertEqual(json.loads((self.output/'recovery.json').read_text())['status'], 'recovered')

    def test_missing_or_malformed_state_and_manifest_retained_as_evidence(self):
        cases = [[], [('.cpc/state', b'root=../escape\nsource=/do/not/write\n')],
                 [('.cpc/state', b'\xff'), ('.cpc/manifest', b'\xfe')],
                 [('.cpc/state', b'root=P\n'), ('.cpc/manifest', b'bad row')],
                 [('.cpc/state', b'root=P\n'), ('.cpc/manifest', b'f\tbad-size\t0\tx\tP/a')]]
        for index, metadata in enumerate(cases):
            with self.subTest(index=index):
                self.output = self.root/str(index)
                self.archive([('P/a', b'a')]+metadata)
                result = self.recover()
                self.assertFalse(result['original_cpc_valid'])
                for name, data in metadata:
                    self.assertEqual((self.output/'metadata'/name).read_bytes(), data)
                state = cpc.read_sidecar_for(str(self.output/'files'))[1]
                self.assertEqual(state['root'], 'files')
                self.assertEqual(state['source'], str(self.output/'recovered.cpc.md'))

    def test_stale_file_hash_is_diagnostic_but_outer_hash_is_mandatory(self):
        manifest = b'd\t0\t0\t-\tP\nf\t1\t0\t'+b'0'*64+b'\tP/a\n'
        self.archive([('P', None), ('P/a', b'a'), ('.cpc/state', b'root=P\n'),
                      ('.cpc/manifest', manifest)])
        result = self.recover()
        self.assertIn('FILE_HASH_MISMATCH', result['first_validation_failure'])
        data = self.cap.read_bytes()
        self.cap.write_bytes(data.replace(data.splitlines()[0].split(b'|')[-1], b'0'*64, 1))
        self.output = self.root/'hash-failure'
        with patch.object(cpc, 'decompress_to_file') as decoder:
            self.assert_rejected('HASH_MISMATCH')
            decoder.assert_not_called()

    def test_member_list_mismatch_keeps_actual_archive_files(self):
        self.archive([('P', None), ('P/a', b'a'), ('P/extra', b'keep'),
                      ('.cpc/state', b'root=P\n'), ('.cpc/manifest', b'd\t0\t0\t-\tP\n')])
        result = self.recover()
        self.assertIn('MANIFEST_MEMBER_MISMATCH', result['first_validation_failure'])
        self.assertEqual((self.output/'files/P/extra').read_bytes(), b'keep')

    def test_never_overwrite_and_reject_inapplicable_options(self):
        self.archive([('P/a', b'a')])
        self.output.mkdir()
        marker = self.output/'keep'
        marker.write_bytes(b'keep')
        with self.assertRaisesRegex(cpc.CPCError, 'DEST_EXISTS'):
            self.recover()
        self.assertEqual(marker.read_bytes(), b'keep')
        for option in ('-f', '-b', '-a', '--report', '--max', '--max-file-size=25MB',
                       '--include=*', '--exclude=*', '--preset=9'):
            self.assertEqual(self.cli('recover', self.cap, '-o', self.root/'new', option)[0], 2)
        self.assertFalse((self.root/'new').exists())

    def test_warning_survives_quiet_and_valid_capsule_is_reported_honestly(self):
        source = self.root/'Project'
        source.mkdir()
        (source/'a').write_bytes(b'a')
        cpc.pack(str(source), str(self.cap), mtime='normalize')
        with self.assertRaisesRegex(cpc.CPCError, 'TIMESTAMPS_UNAVAILABLE'):
            self.recover(mtime='preserve')
        code, out, err = self.cli('recover', self.cap, '-o', self.output, '-q')
        self.assertEqual(code, 0, err)
        self.assertEqual(out, '')
        self.assertIn('CPC RECOVERED', err)
        self.assertNotIn('CPC PASS', err)
        report = json.loads((self.output/'recovery.json').read_text())
        self.assertTrue(report['original_cpc_valid'])
        self.assertEqual(report['mtime'], 'normalize')

    def test_unsafe_names_types_duplicates_and_implicit_parent_conflicts(self):
        for index, entries in enumerate([
            [('../escape', b'x')], [('/absolute', b'x')], [('C:/escape', b'x')],
            [('P/a', b'a'), ('P/a', b'b')], [('P/A', b'a'), ('P/a', b'b')],
            [('P/x/a', b'a'), ('P/X/b', b'b')],
            [('P/a/b', b'b'), ('P/a', b'a')], [('P/a', b'a'), ('P/a/b', b'b')],
        ]):
            with self.subTest(index=index):
                self.archive(entries)
                self.assert_rejected('PATH|NAME|DUPLICATE|COLLISION|CONFLICT')
                code, _, err = self.cli('u', self.cap, '-o', self.output)
                self.assertEqual(code, 2)
                self.assertNotIn('Use cpc recover', err)
        for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE, tarfile.CHRTYPE):
            member = tarfile.TarInfo('P/unsafe')
            member.type, member.linkname = kind, '../outside'
            self.archive([(member, None)])
            self.assert_rejected('UNSUPPORTED_MEMBER_TYPE')

    def test_limits_cannot_be_relaxed_by_recovery(self):
        raw = self.archive([('P/a', b'x'*2048), ('.cpc/state', b'bad')])
        for limit, value, error in [('MAX_CARRIER', 10, 'CARRIER_LIMIT'),
                                    ('MAX_COMPRESSED', 10, 'COMPRESSED_LIMIT'),
                                    ('MAX_TAR', 1024, 'TAR_LIMIT'),
                                    ('MAX_LZMA_MEMORY', 1024, 'DECOMPRESSION_FAILED'),
                                    ('MAX_MEMBERS', 1, 'MEMBER_LIMIT'),
                                    ('MAX_METADATA', 1, 'METADATA_LIMIT'),
                                    ('MAX_EXTENSION', 1, 'EXTENSION_LIMIT'),
                                    ('MAX_FILE', 1, 'FILE_LIMIT'),
                                    ('MAX_TOTAL', 1, 'TOTAL_LIMIT')]:
            with self.subTest(limit=limit), patch.object(cpc, limit, value):
                self.assert_rejected(error)
        self.carrier(packed=lzma.compress(raw)[:-8])
        self.assert_rejected('DECOMPRESSION_FAILED')

    def test_truncated_tar_and_concatenated_tar_rejected(self):
        raw = self.archive([('P/a', b'x'*2048)])
        for malformed in (raw[:1600], raw[:4096]+b'not a tar header'+raw[4112:], raw+raw):
            self.carrier(malformed)
            self.assert_rejected('BAD_TAR|unexpected end')

    def test_implied_directories_count_toward_member_ceiling(self):
        self.archive([('a/b/c/d/e/f', b'x')])
        with patch.object(cpc, 'MAX_MEMBERS', 5):
            self.assert_rejected('MEMBER_LIMIT')

    def test_write_and_timestamp_failures_publish_nothing(self):
        self.archive([('P/a', b'a')])
        for helper in ('write_state_sidecar', 'extract_members'):
            with patch.object(cpc, helper, side_effect=OSError('disk full')):
                with self.assertRaises(OSError):
                    self.recover()
            self.assertFalse(self.output.exists())
            self.assertFalse(list(self.root.glob('.cpc-stage-*')))
        with patch.object(cpc.os, 'utime', side_effect=PermissionError('denied')):
            self.assert_rejected('TIMESTAMP_RESTORE_FAILED')
            self.recover(mtime='normalize')
        self.assertEqual(cpc.read_sidecar_for(str(self.output/'files'))[1]['mtime'], 'normalize')

    def test_invalid_tar_dates_require_explicit_normalization(self):
        member = tarfile.TarInfo('P/a')
        member.pax_headers['mtime'] = 'NaN'
        # Write directly to retain the deliberately invalid timestamp.
        raw = io.BytesIO()
        with tarfile.open(fileobj=raw, mode='w', format=tarfile.PAX_FORMAT) as tf:
            member.size = 1
            tf.addfile(member, io.BytesIO(b'a'))
        self.carrier(raw.getvalue())
        self.assert_rejected('BAD_TIMESTAMP')
        self.recover(mtime='normalize')
        self.assertEqual((self.output/'files/P/a').read_bytes(), b'a')


if __name__ == '__main__':
    unittest.main()
