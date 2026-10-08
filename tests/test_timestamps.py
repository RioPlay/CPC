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
import tarfile
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('cpc', ROOT/'bin/cpc.py')
cpc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cpc)
BASE = 1735689600 * 10**9


class TimestampTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='cpc-times-test-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.project = self.root/'Project'
        self.project.mkdir()
        (self.project/'notes').mkdir()
        (self.project/'empty').mkdir()
        values = {'source.txt': BASE+800_000_000, 'target.out': BASE+100_000_000,
                  'notes/caf\u00e9.txt': BASE+123456700, 'epoch.txt': 0,
                  'negative.txt': -100_000_000, 'future.txt': 4354819200*10**9+123456700}
        for name, value in values.items():
            p = self.project/name
            p.write_bytes(name.encode('utf-8')+b'\r\n')
            os.utime(p, ns=(value, value))
        for p in (self.project/'notes', self.project/'empty', self.project):
            os.utime(p, ns=(BASE+987654300, BASE+987654300))
        self.times = self.tree_times(self.project)
        self.cap = self.root/'original.cpc.md'

    def tree_times(self, root):
        return {'.' if p == root else p.relative_to(root).as_posix(): p.stat().st_mtime_ns
                for p in [root]+list(root.rglob('*'))}

    def cli(self, *args, expected=0):
        with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as error:
            code = cpc.main(list(map(str, args)))
        self.assertEqual(code, expected, error.getvalue())
        return out.getvalue(), error.getvalue()

    def mutate(self, output, edit):
        raw = io.BytesIO()
        with cpc.parse_capsule(str(self.cap)) as info:
            with cpc.open_tar(info['raw']) as source, tarfile.open(fileobj=raw, mode='w', format=tarfile.PAX_FORMAT) as target:
                for member in source:
                    data = source.extractfile(member).read() if member.isfile() else None
                    data = edit(member, data)
                    if data is not None:
                        member.size = len(data)
                    target.addfile(member, io.BytesIO(data) if data is not None else None)
        packed = lzma.compress(raw.getvalue(), preset=6)
        output.write_bytes(f'#CPC|1|b64>xz>tar|{hashlib.sha256(packed).hexdigest()}\n<CPC>\n'.encode()
                           + base64.b64encode(packed)+b'\n</CPC>\n')

    def test_default_restore_and_unchanged_repack(self):
        result = cpc.pack(str(self.project), str(self.cap))
        self.assertEqual(result['mtime'], 'preserve')
        restored, side, info = cpc.unpack(str(self.cap), str(self.root/'restored'), strict=True, keep_state=True)
        self.assertEqual(self.tree_times(Path(restored)), self.times)
        self.assertEqual(cpc.read_sidecar_for(restored)[1]['mtime'], 'preserve')
        self.assertEqual(cpc.inspect_capsule(str(self.cap))['mtime'], 'preserve')
        self.assertGreater((Path(restored)/'source.txt').stat().st_mtime_ns,
                           (Path(restored)/'target.out').stat().st_mtime_ns)
        for member in info['members']:
            if member.name == '.cpc' or member.name.startswith('.cpc/'):
                self.assertEqual(member.mtime, 0)
        returned = self.root/'returned.cpc.md'
        cpc.repack(restored, str(returned))
        self.assertEqual(returned.read_bytes(), self.cap.read_bytes())

    def test_repack_uses_current_times_after_edits(self):
        cpc.pack(str(self.project), str(self.cap))
        restored, _, _ = cpc.unpack(str(self.cap), str(self.root/'restored'), strict=True, keep_state=True)
        tree = Path(restored)
        p = tree/'source.txt'
        p.write_bytes(b'edited')
        ns = BASE+20*10**9+123456700
        os.utime(p, ns=(ns, ns))
        (tree/'new.txt').write_bytes(b'new')
        expected = self.tree_times(tree)
        returned = self.root/'returned.cpc.md'
        cpc.repack(restored, str(returned))
        out, _, _ = cpc.unpack(str(returned), str(self.root/'next'), strict=True, keep_state=True)
        self.assertEqual(self.tree_times(Path(out)), expected)
        self.assertEqual((Path(out)/'source.txt').read_bytes(), b'edited')

    def test_normalized_mode_is_stable_and_inherited(self):
        self.cli('p', self.project, '-o', self.cap, '--normalize-times')
        for p in [self.project]+list(self.project.rglob('*')):
            os.utime(p, ns=(BASE, BASE))
        other = self.root/'other.cpc.md'
        self.cli('p', self.project, '-o', other, '--normalize-times')
        self.assertEqual(self.cap.read_bytes(), other.read_bytes())
        info = cpc.full_verify(str(other))
        self.assertEqual(info['state']['mtime'], 'normalize')
        self.assertTrue(all(cpc.member_mtime_ns(m) == 0 for m in info['members']))
        with patch.object(cpc.os, 'utime') as setter:
            restored, _, _ = cpc.unpack(str(other), str(self.root/'restore'), strict=True, keep_state=True)
            setter.assert_not_called()
        returned = self.root/'returned.cpc.md'
        self.cli('r', restored, '-o', returned)
        self.assertEqual(returned.read_bytes(), other.read_bytes())
        self.cli('r', restored, '-o', self.root/'preserved.cpc.md', '--preserve-times')
        self.assertEqual(cpc.inspect_capsule(str(self.root/'preserved.cpc.md'))['mtime'], 'preserve')

    def test_unpack_override_is_remembered_and_normalized_dates_are_not_invented(self):
        cpc.pack(str(self.project), str(self.cap))
        self.cli('u', self.cap, '-o', self.root/'restore', '--normalize-times', '--state')
        restored = self.root/'restore/Project'
        self.assertEqual(cpc.read_sidecar_for(str(restored))[1]['mtime'], 'normalize')
        normalized = self.root/'normalized.cpc.md'
        cpc.repack(str(restored), str(normalized))
        _, error = self.cli('u', normalized, '-o', self.root/'bad', '--preserve-times', expected=2)
        self.assertIn('TIMESTAMPS_UNAVAILABLE', error)
        self.assertFalse((self.root/'bad').exists())

    def test_legacy_capsule_and_sidecar_keep_normalized_behavior(self):
        cpc.pack(str(self.project), str(self.cap), mtime='normalize')
        legacy = self.root/'legacy.cpc.md'
        def edit(member, data):
            if member.name == '.cpc/state':
                return data.replace(b'mtime=normalize\n', b'')
            return data
        self.mutate(legacy, edit)
        with patch.object(cpc.os, 'utime') as setter:
            restored, side, _ = cpc.unpack(str(legacy), str(self.root/'restore'), strict=True, keep_state=True)
            setter.assert_not_called()
        p = Path(side)
        p.write_text(p.read_text(encoding='utf-8').replace('mtime=normalize\n',''), encoding='utf-8')
        result = cpc.repack(restored, str(self.root/'returned.cpc.md'))
        self.assertEqual(result['mtime'], 'normalize')

    def test_export_inherits_sidecar_and_capsule_export_preserves_bytes(self):
        cpc.pack(str(self.project), str(self.cap), mtime='normalize')
        restored, _, _ = cpc.unpack(str(self.cap), str(self.root/'restore'), strict=True, keep_state=True)
        for override in (None, 'preserve'):
            folder = self.root/('export-'+str(override))
            cpc.export_project(restored, folder, mtime=override)
            cap = next(folder.glob('*.cpc.md'))
            self.assertEqual(cpc.inspect_capsule(str(cap))['mtime'], override or 'normalize')
        cpc.export_project(self.cap, self.root/'exact-export')
        self.assertEqual((self.root/'exact-export'/self.cap.name).read_bytes(), self.cap.read_bytes())
        with self.assertRaisesRegex(cpc.CPCError, 'EXPORT_CAPSULE_OPTIONS'):
            cpc.export_project(self.cap, self.root/'bad-export', mtime='preserve')

    def test_selective_extract_single_file_and_rename_root(self):
        cpc.pack(str(self.project), str(self.cap))
        self.cli('x', self.cap, 'Project/notes', '-o', self.root/'selected')
        self.assertEqual((self.root/'selected/Project/notes').stat().st_mtime_ns, self.times['notes'])
        self.assertEqual((self.root/'selected/Project/notes/caf\u00e9.txt').stat().st_mtime_ns,
                         self.times['notes/caf\u00e9.txt'])
        single = self.root/'single.cpc.md'
        cpc.pack(str(self.project/'source.txt'), str(single))
        restored, _, _ = cpc.unpack(str(single), str(self.root/'single'), strict=True, keep_state=True)
        self.assertEqual(Path(restored).stat().st_mtime_ns, self.times['source.txt'])
        renamed = self.root/'renamed.cpc.md'
        self.cli('n', self.cap, 'Renamed', '-o', renamed)
        restored, _, _ = cpc.unpack(str(renamed), str(self.root/'rename-restore'), strict=True, keep_state=True)
        self.assertEqual(self.tree_times(Path(restored)), self.times)

    def test_timestamp_failure_does_not_replace_existing_destination(self):
        cpc.pack(str(self.project), str(self.cap))
        old = self.root/'restore/Project'
        old.mkdir(parents=True)
        (old/'keep.txt').write_bytes(b'keep')
        with patch.object(cpc.os, 'utime', side_effect=PermissionError('denied')):
            with self.assertRaisesRegex(cpc.CPCError, 'TIMESTAMP_RESTORE_FAILED'):
                cpc.unpack(str(self.cap), str(old.parent), force=True, strict=True, keep_state=True)
        self.assertEqual((old/'keep.txt').read_bytes(), b'keep')
        self.assertFalse(list(old.parent.glob('.cpc-stage-*')))
        self.assertFalse((old.parent/'.Project.cpc-state').exists())

    def test_malformed_dates_and_policy_fail_before_writes(self):
        cpc.pack(str(self.project), str(self.cap))
        mutations = ('nan', 'inf', '1e99999', '1.1234567890', '253402300800', '-62135596801', '9'*10000)
        for i, stamp in enumerate(mutations):
            bad = self.root/f'bad-{i}.cpc.md'
            def edit(member, data):
                if member.name == 'Project/source.txt':
                    member.pax_headers['mtime'] = stamp
                return data
            self.mutate(bad, edit)
            with self.subTest(stamp=stamp[:30]), self.assertRaises(cpc.CPCError):
                cpc.unpack(str(bad), str(self.root/'not-created'), strict=True, keep_state=True)
            self.assertFalse((self.root/'not-created').exists())
        for policy in ('bogus', 'normalize'):
            bad = self.root/(policy+'.cpc.md')
            def edit(member, data):
                if member.name == '.cpc/state':
                    return data.replace(b'mtime=preserve', ('mtime='+policy).encode())
                return data
            self.mutate(bad, edit)
            with self.assertRaises(cpc.CPCError):
                cpc.unpack(str(bad), str(self.root/'not-created'), strict=True, keep_state=True)
            self.assertFalse((self.root/'not-created').exists())

    def test_timestamp_only_change_keeps_content_identity(self):
        a = cpc.pack(str(self.project), str(self.cap))
        os.utime(self.project/'source.txt', ns=(BASE, BASE))
        other = self.root/'changed-date.cpc.md'
        b = cpc.pack(str(self.project), str(other))
        self.assertEqual(a['content_id'], b['content_id'])
        self.assertNotEqual(self.cap.read_bytes(), other.read_bytes())
        self.assertEqual(cpc.compare(str(self.cap), str(self.project))[:3], ([], [], []))

    def test_source_timestamp_change_after_scan_is_detected(self):
        original = cpc.make_manifest
        def change_after_scan(entries):
            result = original(entries)
            os.utime(self.project/'source.txt', ns=(BASE, BASE))
            return result
        with patch.object(cpc, 'make_manifest', side_effect=change_after_scan):
            with self.assertRaisesRegex(cpc.CPCError, 'SOURCE_CHANGED'):
                cpc.pack(str(self.project), str(self.cap))
        self.assertFalse(self.cap.exists())

    def test_timestamp_flags_are_not_silently_ignored(self):
        cpc.pack(str(self.project), str(self.cap))
        for command in ('v','i','c','join'):
            _, error = self.cli(command, self.cap, '--normalize-times', expected=2)
            self.assertIn('TIMESTAMP_OPTION', error)


if __name__ == '__main__':
    unittest.main()
