#!/usr/bin/env python3
# Copyright 2026 RioPlay
# SPDX-License-Identifier: MIT
"""Basic transport, clean workspaces and whole-tree replacement contracts."""
import base64
from contextlib import redirect_stdout, redirect_stderr
import hashlib
import importlib.util
import io
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


class BasicTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='cpc-basic-test-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.cap = self.root/'return.cpc.md'

    def archive(self, entries):
        data = io.BytesIO()
        with tarfile.open(fileobj=data, mode='w', format=tarfile.PAX_FORMAT) as tf:
            for name, contents in entries:
                m = tarfile.TarInfo(name)
                m.mtime = 1735689600
                m.mode = 0o755 if contents is None else 0o644
                if contents is None:
                    m.type = tarfile.DIRTYPE
                else:
                    m.size = len(contents)
                tf.addfile(m, io.BytesIO(contents) if contents is not None else None)
        packed = lzma.compress(data.getvalue(), preset=6)
        self.cap.write_bytes(('#CPC|1|b64>xz>tar|'+hashlib.sha256(packed).hexdigest()
                              +'\n<CPC>\n').encode()+base64.b64encode(packed)+b'\n</CPC>\n')

    def cli(self, *args):
        with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
            code = cpc.main(list(map(str, args)))
        return code, out.getvalue(), err.getvalue()

    def test_missing_metadata_implied_root_and_clean_roundtrip(self):
        self.archive([('Project/src/main.py', b'print(1)\n'), ('Project/empty', None)])
        code, _, warning = self.cli('u', self.cap, '-o', self.root/'work', '-q')
        self.assertEqual(code, 0, warning)
        self.assertIn('optional metadata audit failed', warning)
        tree = self.root/'work/return'
        self.assertEqual(list((self.root/'work').iterdir()), [tree])
        self.assertTrue((tree/'empty').is_dir())
        (tree/'src/main.py').unlink()
        (tree/'new').mkdir()
        (tree/'new/result.txt').write_bytes(b'finished')
        returned = self.root/'updated.cpc.md'
        code, _, err = self.cli('r', tree, '-o', returned)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.cli('v', returned, '--strict')[0], 0)
        self.assertEqual(self.cli('u', returned, '-o', self.root/'next')[0], 0)
        self.assertEqual((self.root/'next/updated/new/result.txt').read_bytes(), b'finished')
        self.assertFalse((self.root/'next/updated/src/main.py').exists())
        self.assertFalse((self.root/'next/.updated.cpc-state').exists())

    def test_strict_is_optional_and_reported(self):
        self.archive([('P/a', b'a')])
        code, out, err = self.cli('v', self.cap)
        self.assertEqual(code, 0, err)
        self.assertIn('metadata=unverified', out)
        self.assertEqual(self.cli('v', self.cap, '--strict')[0], 2)
        self.assertEqual(self.cli('u', self.cap, '-o', self.root/'strict', '--strict')[0], 2)
        self.assertFalse((self.root/'strict').exists())
        self.assertEqual(self.cli(self.cap, '-o', self.root/'auto')[0], 0)

    def test_versioned_capsules_restore_beside_original_and_roundtrip(self):
        project = self.root/'Project'
        project.mkdir()
        (project/'run.sh').write_bytes(b'#!/bin/sh\necho original\n')
        (project/'empty').mkdir()
        v2, v3 = self.root/'Project-v2.cpc.md', self.root/'Project-v3.cpc.md'
        cpc.pack(str(project), str(v2), file_exec={'run.sh': True})
        original_capsule = v2.read_bytes()
        v3.write_bytes(original_capsule)
        self.assertEqual(self.cli(v2)[0], 0)
        code, out, err = self.cli('u', v3, '--strict', '--state')
        self.assertEqual(code, 0, err)
        tree = self.root/'Project-v3'
        self.assertIn(str(tree), out)
        self.assertTrue((self.root/'Project-v2/empty').is_dir())
        self.assertTrue((tree/'empty').is_dir())
        self.assertFalse((tree/'Project').exists())
        self.assertEqual((tree/'run.sh').read_bytes(), (project/'run.sh').read_bytes())
        self.assertEqual(tree.stat().st_mtime_ns, project.stat().st_mtime_ns)
        state = cpc.read_sidecar_for(str(tree))[1]
        self.assertEqual(state['root'], 'Project-v3')
        self.assertIs(cpc.recorded_executable_intent(state)['run.sh'], True)
        self.assertEqual(self.cli('c', v3, tree)[0], 0)
        (tree/'run.sh').write_bytes(b'#!/bin/sh\necho edited\n')
        self.assertEqual(self.cli('c', v3, tree)[0], 1)
        returned = self.root/'Project-v4.cpc.md'
        self.assertEqual(self.cli('r', tree, '-o', returned)[0], 0)
        self.assertEqual(self.cli('v', returned, '--strict')[0], 0)
        self.assertEqual(self.cli(returned, '--state')[0], 0)
        self.assertEqual((self.root/'Project-v4/run.sh').read_bytes(), (tree/'run.sh').read_bytes())
        self.assertTrue((self.root/'Project-v4/empty').is_dir())
        self.assertEqual(v2.read_bytes(), original_capsule)
        self.assertEqual(v3.read_bytes(), original_capsule)
        self.assertEqual((project/'run.sh').read_bytes(), b'#!/bin/sh\necho original\n')

    def test_original_root_option_and_explicit_parent(self):
        self.archive([('Archived/src/a', b'a')])
        self.assertEqual(self.cli('u', self.cap, '-o', self.root/'default')[0], 0)
        self.assertEqual((self.root/'default/return/src/a').read_bytes(), b'a')
        for verb in (('u', self.cap), (self.cap,)):
            parent = self.root/('explicit' if len(verb) == 2 else 'auto')
            code, _, err = self.cli(*verb, '-o', parent, '--original-root')
            self.assertEqual(code, 0, err)
            self.assertEqual((parent/'Archived/src/a').read_bytes(), b'a')
            code, _, err = self.cli(*verb, '-o', parent, '--original-root')
            self.assertEqual(code, 2)
            self.assertIn('DEST_EXISTS', err)
            self.assertIn('-b (backup)', err)
            self.assertEqual((parent/'Archived/src/a').read_bytes(), b'a')

    def test_capsule_folder_suffixes_and_unsafe_names(self):
        for name, expected in (('Project-v2.cpc.md', 'Project-v2'),
                               ('Project.v2.CPC.MD', 'Project.v2'),
                               ('Project (1).cpc.md', 'Project (1)'),
                               ('renamed.md', 'renamed')):
            self.assertEqual(cpc.capsule_folder_name(name), expected)
        for name in ('.cpc.md', 'CON.cpc.md', '.cpc.cpc.md', 'bad\x01.cpc.md'):
            with self.assertRaisesRegex(cpc.CPCError, 'CAPSULE_NAME'):
                cpc.capsule_folder_name(name)
        self.archive([('P/a', b'a')])
        invalid = self.root/'.cpc.md'
        invalid.write_bytes(self.cap.read_bytes())
        self.assertEqual(self.cli(invalid)[0], 2)
        self.assertEqual(self.cli(invalid, '--original-root')[0], 0)
        self.assertEqual((self.root/'P/a').read_bytes(), b'a')

    def test_extensionless_capsule_cannot_be_replaced_by_its_output(self):
        self.archive([('P/a', b'a')])
        bare = self.root/'capsule'
        bare.write_bytes(self.cap.read_bytes())
        for flag in ('-f', '-b'):
            code, _, err = self.cli(bare, flag)
            self.assertEqual(code, 2)
            self.assertIn('OUTPUT_IS_CAPSULE', err)
            self.assertEqual(bare.read_bytes(), self.cap.read_bytes())
        self.assertEqual(self.cli(bare, '-o', self.root/'elsewhere')[0], 0)
        self.assertEqual((self.root/'elsewhere/capsule/a').read_bytes(), b'a')

    def test_bad_metadata_never_controls_destination_or_file_selection(self):
        for index, metadata in enumerate([
            [('.cpc/state', b'root=../../elsewhere\nsource=/overwrite\n')],
            [('.cpc/state', b'\xff'), ('.cpc/manifest', b'\xff')],
            [('.cpc/state', b'root=P\n'), ('.cpc/manifest', b'd\t0\t0\t-\tP\n')],
            [('.cpc/state', b'root=P\n'), ('.cpc/manifest',
              b'd\t0\t0\t-\tP\nf\t1\t0\t'+b'0'*64+b'\tP/a\n')],
        ]):
            with self.subTest(index=index):
                self.archive([('P', None), ('P/a', b'a')]+metadata)
                dest = self.root/str(index)
                code, _, err = self.cli('u', self.cap, '-o', dest)
                self.assertEqual(code, 0, err)
                self.assertEqual((dest/'return/a').read_bytes(), b'a')
                self.assertFalse((dest/'.cpc').exists())
                self.assertEqual(len(list(dest.iterdir())), 1)

    def test_multiple_roots_require_explicit_whole_destination(self):
        self.archive([('one/a', b'a'), ('two/b', b'b'), ('readme.txt', b'hi')])
        code, _, err = self.cli('u', self.cap)
        self.assertEqual(code, 2)
        self.assertIn('MULTIPLE_ROOTS', err)
        dest = self.root/'bundle'
        self.assertEqual(self.cli('u', self.cap, '-o', dest)[0], 0)
        self.assertEqual(sorted(p.name for p in dest.iterdir()), ['one', 'readme.txt', 'two'])
        (dest/'obsolete').write_bytes(b'old')
        self.assertEqual(self.cli('u', self.cap, '-o', dest, '-b')[0], 0)
        self.assertTrue((self.root/'bundle.bak/obsolete').exists())
        self.assertFalse((dest/'obsolete').exists())

    def test_replace_and_numbered_backups_match_returned_tree(self):
        self.archive([('P/a', b'new')])
        dest = self.root/'work'
        tree = dest/'return'
        tree.mkdir(parents=True)
        (tree/'obsolete').write_bytes(b'old')
        self.assertEqual(self.cli('u', self.cap, '-o', dest)[0], 2)
        self.assertTrue((tree/'obsolete').exists())
        self.assertEqual(self.cli('u', self.cap, '-o', dest, '-b')[0], 0)
        self.assertEqual((dest/'return.bak/obsolete').read_bytes(), b'old')
        self.assertEqual(self.cli('u', self.cap, '-o', dest, '-b')[0], 0)
        self.assertTrue((dest/'return.bak1/a').exists())
        (tree/'extra').write_bytes(b'extra')
        self.assertEqual(self.cli('u', self.cap, '-o', dest, '-f')[0], 0)
        self.assertEqual([p.name for p in tree.iterdir()], ['a'])

    def test_failed_staging_and_corruption_do_not_touch_old_tree(self):
        self.archive([('P/a', b'new')])
        dest = self.root/'work'
        tree = dest/'return'
        tree.mkdir(parents=True)
        (tree/'keep').write_bytes(b'old')
        with patch.object(cpc, 'extract_members', side_effect=OSError('disk full')):
            self.assertEqual(self.cli('u', self.cap, '-o', dest, '-f')[0], 2)
        self.assertEqual((tree/'keep').read_bytes(), b'old')
        self.assertFalse(list(dest.glob('.cpc-stage-*')))
        data = self.cap.read_bytes()
        self.cap.write_bytes(data.replace(data.splitlines()[0].split(b'|')[-1], b'0'*64, 1))
        code, _, err = self.cli('u', self.cap, '-o', dest, '-f')
        self.assertEqual(code, 2)
        self.assertIn('HASH_MISMATCH', err)
        self.assertEqual((tree/'keep').read_bytes(), b'old')

    def test_state_is_opt_in_and_stale_state_cannot_be_silently_reused(self):
        self.archive([('P/a', b'a')])
        dest = self.root/'work'
        self.assertEqual(self.cli('u', self.cap, '-o', dest, '--state')[0], 0)
        self.assertTrue((dest/'.return.cpc-state').is_file())
        before = (dest/'.return.cpc-state').read_bytes()
        code, _, err = self.cli('u', self.cap, '-o', dest, '-f')
        self.assertEqual(code, 2)
        self.assertIn('STATE_EXISTS', err)
        self.assertEqual((dest/'.return.cpc-state').read_bytes(), before)
        self.assertEqual(self.cli('u', self.cap, '-o', dest, '-f', '--state')[0], 0)

    def test_publication_failure_rolls_back_whole_tree(self):
        self.archive([('P/a', b'new')])
        dest = self.root/'work'
        tree = dest/'return'
        tree.mkdir(parents=True)
        (tree/'keep').write_bytes(b'old')
        original = cpc.os.replace
        def fail_stage(source, target):
            if '.cpc-stage-' in str(source) and Path(target) == tree:
                raise PermissionError('blocked publication')
            return original(source, target)
        with patch.object(cpc.os, 'replace', side_effect=fail_stage):
            self.assertEqual(self.cli('u', self.cap, '-o', dest, '-b')[0], 2)
        self.assertEqual((tree/'keep').read_bytes(), b'old')
        self.assertFalse((dest/'return.bak').exists())
        retained, = dest.glob('.cpc-stage-*')
        self.assertEqual((retained/'P/a').read_bytes(), b'new')

    def test_windows_rename_retries_only_known_errors_and_is_bounded(self):
        for winerror in (5, 32, 33, 112, None):
            with self.subTest(winerror=winerror):
                error = PermissionError('injected denial')
                error.winerror = winerror
                with patch.object(cpc.os, 'replace', side_effect=error) as rename, \
                     patch.object(cpc.time, 'sleep') as sleep, \
                     redirect_stderr(io.StringIO()) as err:
                    with self.assertRaises(PermissionError):
                        cpc.rename_extraction('source', 'destination')
                retryable = winerror in (5, 32, 33)
                self.assertEqual(rename.call_count, 7 if retryable else 1)
                self.assertAlmostEqual(sum(call.args[0] for call in sleep.call_args_list),
                                       3.15 if retryable else 0)
                self.assertEqual(err.getvalue().count('CPC WARN'), int(retryable))
                if retryable:
                    with patch.object(cpc.os, 'replace', side_effect=[error, None]) as rename, \
                         patch.object(cpc.time, 'sleep'), redirect_stderr(io.StringIO()):
                        cpc.rename_extraction('source', 'destination')
                    self.assertEqual(rename.call_count, 2)

    def test_failed_publication_retains_each_extraction_layout(self):
        for layout in ('root', 'flat', 'selected', 'recovery'):
            with self.subTest(layout=layout):
                dest = self.root/layout
                self.archive([('a', b'new'), ('b', b'b')] if layout == 'flat'
                             else [('P/a', b'new')])
                args = ('recover', self.cap, '-o', dest) if layout == 'recovery' else (
                    ('x', self.cap, 'P/a', '-o', dest) if layout == 'selected'
                    else ('u', self.cap, '-o', dest, '-q'))
                original = cpc.os.replace
                def fail_publish(source, target):
                    # Allow recovery's staged state/report writes.
                    if Path(source).is_dir():
                        raise PermissionError('persistent publication denial')
                    return original(source, target)
                with patch.object(cpc.os, 'replace', side_effect=fail_publish):
                    code, _, err = self.cli(*args)
                self.assertEqual(code, 2)
                self.assertIn('PUBLISH_FAILED', err)
                retained = Path(err.split('Extracted project retained at: ', 1)[1].splitlines()[0])
                self.assertTrue(retained.is_dir())
                content = retained / ('files/P/a' if layout == 'recovery' else
                                      'P/a' if layout == 'selected' else 'a')
                self.assertEqual(content.read_bytes(), b'new')
                if layout == 'recovery':
                    self.assertTrue((retained/'recovery.json').is_file())
                    self.assertTrue((retained/'.files.cpc-state').is_file())
                self.assertFalse((dest/'return').exists() if layout == 'root' else dest.exists())

    def test_failed_rollback_retains_both_projects(self):
        self.archive([('P/a', b'new')])
        for flag in ('-f', '-b'):
            with self.subTest(flag=flag):
                dest = self.root/flag[1:]
                tree = dest/'return'
                tree.mkdir(parents=True)
                (tree/'keep').write_bytes(b'old')
                original = cpc.os.replace
                def block_destination(source, target):
                    if Path(target) == tree:
                        raise PermissionError('publication and rollback denied')
                    return original(source, target)
                with patch.object(cpc.os, 'replace', side_effect=block_destination):
                    code, _, err = self.cli('u', self.cap, '-o', dest, flag)
                self.assertEqual(code, 2)
                self.assertIn('Rollback also failed', err)
                new = Path(err.split('Extracted project retained at: ', 1)[1].splitlines()[0])
                old = Path(err.split('Previous project retained at: ', 1)[1].splitlines()[0])
                self.assertEqual((new/'a').read_bytes(), b'new')
                self.assertEqual((old/'keep').read_bytes(), b'old')
                self.assertFalse(tree.exists())

    def test_locked_old_destination_is_untouched_and_new_tree_retained(self):
        self.archive([('P/a', b'new')])
        tree = self.root/'return'
        tree.mkdir()
        (tree/'keep').write_bytes(b'old')
        with patch.object(cpc.os, 'replace', side_effect=PermissionError('old tree locked')):
            code, _, err = self.cli('u', self.cap, '-o', self.root, '-f')
        self.assertEqual(code, 2)
        self.assertIn('saving the previous destination', err)
        self.assertEqual((tree/'keep').read_bytes(), b'old')
        retained, = self.root.glob('.cpc-stage-*')
        self.assertEqual((retained/'P/a').read_bytes(), b'new')
        self.assertFalse(list(self.root.glob('.cpc-old-*')))

    @unittest.skipUnless(os.name == 'nt', 'Windows directory-handle sharing semantics')
    def test_real_windows_directory_lock_recovers_after_release(self):
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateFileW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                      wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD,
                                      wintypes.HANDLE)
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel.CloseHandle.restype = wintypes.BOOL
        self.archive([('P/a', b'new')])
        extract = cpc.extract_members
        handles = []
        def release(_delay=None):
            while handles:
                self.assertTrue(kernel.CloseHandle(handles.pop()))
        self.addCleanup(release)
        def extract_and_lock(*args, **kwargs):
            extract(*args, **kwargs)
            staged = Path(args[2])/'P'
            # FILE_SHARE_READ | FILE_SHARE_WRITE, deliberately no SHARE_DELETE.
            locked = staged/'a' if lock_child else staged
            handle = kernel.CreateFileW(str(locked), 0x80000000, 3, None, 3, 0x02000000, None)
            if handle == wintypes.HANDLE(-1).value:
                raise ctypes.WinError(ctypes.get_last_error())
            handles.append(handle)
            with self.assertRaises(OSError) as blocked:
                os.replace(staged, self.root/'probe')
            self.assertIn(blocked.exception.winerror, (5, 32, 33))
        for lock_child, persistent in ((False, False), (False, True), (True, False), (True, True)):
            with self.subTest(lock_child=lock_child, persistent=persistent):
                dest = self.root/f'child-{lock_child}-persistent-{persistent}'
                with patch.object(cpc, 'extract_members', side_effect=extract_and_lock), \
                     patch.object(cpc.time, 'sleep', side_effect=None if persistent else release) as sleep:
                    code, _, err = self.cli('u', self.cap, '-o', dest)
                release()
                self.assertIn('retrying', err)
                self.assertEqual(sleep.call_count, 6 if persistent else 1)
                self.assertEqual(code, 2 if persistent else 0, err)
                if persistent:
                    retained = Path(err.split('Extracted project retained at: ', 1)[1].splitlines()[0])
                    self.assertEqual((retained/'a').read_bytes(), b'new')
                    self.assertFalse((dest/'return').exists())
                else:
                    self.assertEqual((dest/'return/a').read_bytes(), b'new')
                    self.assertFalse(list(dest.glob('.cpc-stage-*')))

    def test_multiple_roots_optional_state_and_single_file(self):
        self.archive([('a/x', b'x'), ('b/y', b'y')])
        dest = self.root/'collection'
        self.assertEqual(self.cli('u', self.cap, '-o', dest, '--state')[0], 0)
        state = cpc.read_sidecar_for(str(dest))[1]
        self.assertEqual(state['root'], 'collection')
        self.assertEqual(set(cpc.recorded_executable_intent(state)), {'a/x', 'b/y'})
        self.assertEqual(self.cli('r', dest, '-o', self.root/'new.cpc.md')[0], 0)
        self.assertEqual(self.cli('v', self.root/'new.cpc.md', '--strict')[0], 0)
        self.archive([('file.txt', b'single')])
        self.assertEqual(self.cli('u', self.cap, '-o', self.root/'single')[0], 0)
        self.assertEqual((self.root/'single/file.txt').read_bytes(), b'single')

    def test_options_are_not_silently_ignored(self):
        for command in ('p', 'r', 'export', 'recover', 'join', 'i', 'l', 'c', 'x', 'n'):
            for option in ('--state', '--strict', '--original-root'):
                code, _, err = self.cli(command, option)
                self.assertEqual(code, 2)
                self.assertIn('OPTION', err)

    def test_basic_capsule_survives_export_join_and_fresh_unpack(self):
        self.archive([('P/a', b'a')])
        with redirect_stderr(io.StringIO()):
            result = cpc.export_capsule(self.cap, self.root/'export')
        self.assertFalse(result['split'])
        self.assertEqual((self.root/'export/return.cpc.md').read_bytes(), self.cap.read_bytes())
        # Exercise paired transport with a large opaque file and fresh receiver.
        import random
        rng = random.Random(0)
        self.archive([('P/data.bin', bytes(rng.getrandbits(8) for _ in range(130000)))])
        with redirect_stderr(io.StringIO()):
            result = cpc.export_capsule(self.cap, self.root/'parts', 131072)
            cpc.join_parts([self.root/'parts'], self.root/'joined.cpc.md')
        self.assertTrue(result['split'])
        self.assertEqual(self.cli('u', self.root/'joined.cpc.md', '-o', self.root/'joined-out')[0], 0)
        self.assertEqual((self.root/'joined-out/joined/data.bin').stat().st_size, 130000)

    def test_unsafe_paths_still_fail_before_replacement(self):
        for path in ('../escape', '/absolute', 'P/../escape'):
            self.archive([(path, b'x')])
            code, _, err = self.cli('u', self.cap, '-o', self.root/'unsafe', '-f')
            self.assertEqual(code, 2)
            self.assertIn('UNSAFE_PATH', err)
            self.assertFalse((self.root/'unsafe').exists())


if __name__ == '__main__':
    unittest.main()
