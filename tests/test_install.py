#!/usr/bin/env python3
"""Installation updates, command selection and wrapper argument forwarding."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class InstallTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='cpc-install-test-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.bindir = self.root/'installed bin'
        self.env = dict(os.environ)
        self.env['PATH'] = str(self.bindir) + os.pathsep + self.env.get('PATH', '')

    def install(self, *extra):
        result = subprocess.run([sys.executable, str(ROOT/'bootstrap.py'),
                                 '--prefix', str(self.bindir), *extra],
                                env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def test_update_overwrites_old_core_and_runs_latest_installed_launcher(self):
        self.bindir.mkdir()
        (self.bindir/'cpc.py').write_text('raise RuntimeError("old install")\n')
        result = self.install()
        source = (ROOT/'bin/cpc.py').read_bytes()
        self.assertEqual((self.bindir/'cpc.py').read_bytes(), source)
        self.assertIn(hashlib.sha256(source).hexdigest(), result.stdout)
        self.assertIn('PATH selects this installation:', result.stdout)
        launch = self.bindir/('cpc.cmd' if os.name == 'nt' else 'cpc')
        command = ([os.environ.get('COMSPEC', 'cmd.exe'), '/d', '/c', str(launch)]
                   if os.name == 'nt' else [str(launch)])
        installed = subprocess.run(command + ['--version'], capture_output=True, text=True)
        expected = subprocess.run([sys.executable, str(ROOT/'bin/cpc.py'), '--version'],
                                  capture_output=True, text=True, check=True)
        self.assertEqual(installed.returncode, 0, installed.stderr)
        self.assertEqual(installed.stdout.strip(), expected.stdout.strip())

    def test_shadowed_install_is_reported_without_replacing_other_copy(self):
        older = self.root/'older bin'
        older.mkdir()
        old = older/('cpc.cmd' if os.name == 'nt' else 'cpc')
        original = b'@echo old-cpc\r\n' if os.name == 'nt' else b'#!/bin/sh\necho old-cpc\n'
        old.write_bytes(original)
        old.chmod(0o755)
        self.env['PATH'] = str(older) + os.pathsep + self.env['PATH']
        result = self.install()
        self.assertIn('WARNING: PATH selects a different CPC:', result.stderr)
        self.assertIn(str(older), result.stderr)
        self.assertEqual(old.read_bytes(), original)
        self.assertEqual((self.bindir/'cpc.py').read_bytes(), (ROOT/'bin/cpc.py').read_bytes())

    def test_missing_path_is_reported(self):
        self.env['PATH'] = str(self.root/'empty path')
        result = self.install()
        self.assertIn('WARNING: cpc is not on PATH.', result.stderr)

    def test_uninstall_keeps_unrelated_files(self):
        self.install()
        keep = self.bindir/'unrelated.txt'
        keep.write_text('keep')
        self.install('--uninstall')
        self.assertEqual(list(self.bindir.iterdir()), [keep])

    @unittest.skipIf(os.name == 'nt', 'POSIX wrapper is exercised by Linux/macOS CI')
    def test_shell_wrapper_forwards_prefix_and_uninstall(self):
        found = shutil.which('sh')
        shell = Path(found) if found else None
        if shell is None or not shell.is_file():
            self.skipTest('A POSIX shell is required')
        fake = self.root/'fake python'
        fake.mkdir()
        python = fake/'python3'
        python.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n', encoding='utf-8')
        python.chmod(0o755)
        env = dict(self.env)
        env['PATH'] = str(fake) + os.pathsep + env['PATH']
        target = str(self.bindir)
        result = subprocess.run([str(shell), (ROOT/'install.sh').as_posix(),
                                 '--prefix', target, '--uninstall'],
                                env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        args = result.stdout.splitlines()
        self.assertEqual(Path(args[0]).name, 'bootstrap.py')
        self.assertEqual(args[1:], ['--prefix', target, '--uninstall'])
        self.assertFalse(self.bindir.exists())

    @unittest.skipUnless(os.name == 'nt', 'PowerShell wrapper runs on Windows')
    def test_powershell_wrapper_forwards_prefix_and_exit_status(self):
        shell = shutil.which('powershell') or shutil.which('pwsh')
        if not shell:
            self.skipTest('PowerShell is required')
        command = [shell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(ROOT/'install.ps1')]
        result = subprocess.run(command + ['--prefix', str(self.bindir)], env=self.env,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.bindir/'cpc.py').read_bytes(), (ROOT/'bin/cpc.py').read_bytes())
        bad = subprocess.run(command + ['--not-an-option'], env=self.env,
                             capture_output=True, text=True)
        self.assertNotEqual(bad.returncode, 0)


if __name__ == '__main__':
    unittest.main()
