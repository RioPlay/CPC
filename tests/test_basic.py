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
        tree = self.root/'work/Project'
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
        self.assertEqual((self.root/'next/Project/new/result.txt').read_bytes(), b'finished')
        self.assertFalse((self.root/'next/Project/src/main.py').exists())
        self.assertFalse((self.root/'next/.Project.cpc-state').exists())

    def test_strict_is_optional_and_reported(self):
        self.archive([('P/a', b'a')])
        code, out, err = self.cli('v', self.cap)
        self.assertEqual(code, 0, err)
        self.assertIn('metadata=unverified', out)
        self.assertEqual(self.cli('v', self.cap, '--strict')[0], 2)
        self.assertEqual(self.cli('u', self.cap, '-o', self.root/'strict', '--strict')[0], 2)
        self.assertFalse((self.root/'strict').exists())
        self.assertEqual(self.cli(self.cap, '-o', self.root/'auto')[0], 0)

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
                self.assertEqual((dest/'P/a').read_bytes(), b'a')
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
        tree = dest/'P'
        tree.mkdir(parents=True)
        (tree/'obsolete').write_bytes(b'old')
        self.assertEqual(self.cli('u', self.cap, '-o', dest)[0], 2)
        self.assertTrue((tree/'obsolete').exists())
        self.assertEqual(self.cli('u', self.cap, '-o', dest, '-b')[0], 0)
        self.assertEqual((dest/'P.bak/obsolete').read_bytes(), b'old')
        self.assertEqual(self.cli('u', self.cap, '-o', dest, '-b')[0], 0)
        self.assertTrue((dest/'P.bak1/a').exists())
        (tree/'extra').write_bytes(b'extra')
        self.assertEqual(self.cli('u', self.cap, '-o', dest, '-f')[0], 0)
        self.assertEqual([p.name for p in tree.iterdir()], ['a'])

    def test_failed_staging_and_corruption_do_not_touch_old_tree(self):
        self.archive([('P/a', b'new')])
        dest = self.root/'work'
        tree = dest/'P'
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
        self.assertTrue((dest/'.P.cpc-state').is_file())
        before = (dest/'.P.cpc-state').read_bytes()
        code, _, err = self.cli('u', self.cap, '-o', dest, '-f')
        self.assertEqual(code, 2)
        self.assertIn('STATE_EXISTS', err)
        self.assertEqual((dest/'.P.cpc-state').read_bytes(), before)
        self.assertEqual(self.cli('u', self.cap, '-o', dest, '-f', '--state')[0], 0)

    def test_publication_failure_rolls_back_whole_tree(self):
        self.archive([('P/a', b'new')])
        dest = self.root/'work'
        tree = dest/'P'
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
        self.assertFalse((dest/'P.bak').exists())
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
            for option in ('--state', '--strict'):
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
        self.assertEqual((self.root/'joined-out/P/data.bin').stat().st_size, 130000)

    def test_unsafe_paths_still_fail_before_replacement(self):
        for path in ('../escape', '/absolute', 'P/../escape'):
            self.archive([(path, b'x')])
            code, _, err = self.cli('u', self.cap, '-o', self.root/'unsafe', '-f')
            self.assertEqual(code, 2)
            self.assertIn('UNSAFE_PATH', err)
            self.assertFalse((self.root/'unsafe').exists())


if __name__ == '__main__':
    unittest.main()
