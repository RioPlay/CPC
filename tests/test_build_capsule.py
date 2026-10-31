#!/usr/bin/env python3
# Copyright 2026 RioPlay
# SPDX-License-Identifier: MIT
"""Release checks compare source bytes without rewriting the capsule or tree."""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('build_capsule', ROOT/'tools/build_capsule.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class ReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temp = tempfile.TemporaryDirectory(prefix='cpc-release-tests-')
        cls.addClassCleanup(temp.cleanup)
        cls.template = Path(temp.name)/'source'
        for name in builder.FILES:
            target = cls.template/name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT/name, target)
        result = cls.command(cls.template, 'tools/build_capsule.py')
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='cpc-release-case-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)/'source'
        shutil.copytree(self.template, self.root, ignore=shutil.ignore_patterns('__pycache__'))

    @staticmethod
    def command(root, script, *args):
        env = dict(os.environ)
        env.pop('PYTHONDONTWRITEBYTECODE', None)
        return subprocess.run(
            [sys.executable, str(root/script), *map(str, args)],
            cwd=root, capture_output=True, text=True,
            env=env,
        )

    def snapshot(self):
        return {p.relative_to(self.root).as_posix():
                (p.read_bytes() if p.is_file() else None, p.stat().st_mtime_ns)
                for p in [self.root] + list(self.root.rglob('*'))}

    def check(self, success=True):
        before = self.snapshot()
        result = self.command(self.root, 'tools/build_capsule.py', '--check')
        self.assertEqual(self.snapshot(), before, '--check modified the source tree')
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('CPC release capsule verified:', result.stdout)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn('CPC release capsule verified:', result.stdout)
        return result.stdout + result.stderr

    def test_fresh_capsule_matches(self):
        self.check()

    def test_changed_bytes_with_same_size_and_time_fail_then_rebuild_passes(self):
        for name in ('README.md', 'standard/README.md'):
            source = self.root/name
            stat = source.stat()
            original = source.read_bytes()
            source.write_bytes(bytes([original[0] ^ 1]) + original[1:])
            os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        message = self.check(success=False)
        self.assertIn('Release content mismatch:', message)
        self.assertIn("'README.md'", message)
        self.assertIn("'standard/README.md'", message)
        rebuilt = self.command(self.root, 'tools/build_capsule.py')
        self.assertEqual(rebuilt.returncode, 0, rebuilt.stdout + rebuilt.stderr)
        self.check()

    def test_changed_timestamp_with_same_bytes_passes(self):
        source = self.root/'README.md'
        stamp = source.stat().st_mtime_ns + 10_000_000_000
        os.utime(source, ns=(stamp, stamp))
        self.check()

    def test_stale_receiver_fails_even_when_project_bytes_match(self):
        capsule = self.root/'CPC.cpc.md'
        data = capsule.read_bytes()
        marker = b'<!-- CPC-RECEIVER|1|b64>xz|'
        offset = data.index(marker)+len(marker)
        capsule.write_bytes(data[:offset]+b'0'*64+data[offset+64:])
        self.assertIn('Release receiver mismatch', self.check(success=False))

    @unittest.skipUnless(shutil.which('git'), 'Git is required for checkout regression')
    def test_capsule_matches_with_either_autocrlf_setting(self):
        def git(*args):
            result = subprocess.run(
                ['git', '-C', str(self.root), *args],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        git('init', '-q')
        git('config', 'core.autocrlf', 'false')
        git('add', '--force', '--', *builder.FILES)
        for autocrlf in ('false', 'true'):
            with self.subTest(autocrlf=autocrlf):
                git('config', 'core.autocrlf', autocrlf)
                for name in builder.FILES:
                    (self.root/name).unlink()
                git('checkout-index', '--force', '--all')
                self.check()

    def test_missing_source_fails(self):
        (self.root/'README.md').unlink()
        self.assertIn('README.md', self.check(success=False))

    def test_allowlist_mismatch_is_still_rejected(self):
        stage = Path(self.root.parent)/'CPC'
        for name in builder.FILES:
            if name == 'README.md':
                continue
            target = stage/name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.root/name, target)
        (stage/'unexpected.txt').write_bytes(b'extra')
        packed = self.command(self.root, 'bin/cpc.py', 'p', stage, '-a',
                              '-o', self.root/'CPC.cpc.md', '-f')
        self.assertEqual(packed.returncode, 0, packed.stdout + packed.stderr)
        message = self.check(success=False)
        self.assertIn('Release file mismatch:', message)
        self.assertIn('CPC/README.md', message)
        self.assertIn('CPC/unexpected.txt', message)

    def test_corruption_is_still_rejected(self):
        capsule = self.root/'CPC.cpc.md'
        data = capsule.read_bytes()
        start = data.index(b'<CPC>') + len(b'<CPC>')
        index = next(i for i in range(start, len(data)) if not chr(data[i]).isspace())
        replacement = b'A' if data[index:index+1] != b'A' else b'B'
        capsule.write_bytes(data[:index] + replacement + data[index+1:])
        self.check(success=False)


if __name__ == '__main__':
    unittest.main()
