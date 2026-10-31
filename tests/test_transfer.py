#!/usr/bin/env python3
# Copyright 2026 RioPlay
# SPDX-License-Identifier: MIT
"""Exercise the attachment's own instructions in isolated Python processes."""
import base64
import hashlib
import importlib.util
import json
import lzma
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('cpc', ROOT/'bin/cpc.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class HandoffTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='cpc-handoff-test-')
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.source = self.root/'Project with spaces'
        self.source.mkdir()
        (self.source/'empty').mkdir()
        (self.source/'café.txt').write_text('hello\nこんにちは\n', encoding='utf-8')
        (self.source/'opaque.bin').write_bytes(random.Random(31).randbytes(16000))
        (self.source/'run.py').write_text('raise RuntimeError("PROJECT_MUST_NOT_RUN")\n')
        os.utime(self.source/'run.py', ns=(1700000000123456700, 1700000000123456700))
        self.cap = self.root/'original.cpc.md'
        m.pack(str(self.source), str(self.cap), archive_mode=True,
               file_exec={'run.py': True})

    def run_tool(self, cli, cwd, *args, ok=True):
        result = subprocess.run([sys.executable, '-I', str(cli), *map(str, args)],
                                cwd=cwd, capture_output=True, text=True, timeout=30)
        if ok:
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout+result.stderr)
        return result

    def cold(self, capsule=None):
        out = self.root/'export'
        m.export_project(str(capsule or self.cap), str(out), self_contained=True)
        attachment = next(out.glob('*.cpc.md'))
        cold = self.root/'fresh'
        cold.mkdir()
        shutil.copyfile(attachment, cold/'input.cpc.md')
        text = attachment.read_text(encoding='utf-8')
        # Follow the guide, not an import from the development checkout.
        script = text.split('```python\n', 1)[1].split('```', 1)[0]
        (cold/'cpc-bootstrap.py').write_text(script, encoding='utf-8')
        return cold

    def bootstrap(self, cold, ok=True):
        return self.run_tool(cold/'cpc-bootstrap.py', cold, 'input.cpc.md', ok=ok)

    def test_single_attachment_cold_restore_edit_return(self):
        cold = self.cold()
        self.bootstrap(cold)
        cli = cold/'cpc-tools/cpc-recover.py'
        self.assertEqual(cli.read_bytes(), (ROOT/'bin/cpc.py').read_bytes())
        result = self.run_tool(cli, cold, 'restore', 'input.cpc.md', '-o', 'restored')
        self.assertIn('CPC RESTORED AND VERIFIED', result.stdout)
        self.assertNotIn('PROJECT_MUST_NOT_RUN', result.stdout+result.stderr)
        receipt = json.loads((cold/'restored/RESTORE.json').read_text())
        work = Path(receipt['workspace'])
        self.assertFalse(receipt['project_code_executed'])
        self.assertEqual(receipt['read_back'], 'equal')
        self.assertEqual(receipt['files'], 3)
        self.assertTrue((work/'empty').is_dir())
        for path in self.source.iterdir():
            if path.is_file():
                self.assertEqual((work/path.name).read_bytes(), path.read_bytes())
                self.assertEqual((work/path.name).stat().st_mtime_ns, path.stat().st_mtime_ns)
        self.assertTrue(Path(receipt['state']).is_file())
        if os.name != 'nt':
            self.assertTrue((work/'run.py').stat().st_mode & 0o111)
        (work/'café.txt').write_text('authorized edit\n', encoding='utf-8')
        self.run_tool(cli, cold, 'export', work, '-o', 'return-files')
        returned = list((cold/'return-files').iterdir())
        self.assertEqual(len(returned), 1)
        self.assertIn(b'CPC-RECEIVER|1|', returned[0].read_bytes())
        self.assertEqual(m.compare(str(returned[0]), str(work))[:3], ([], [], []))

    def test_reexport_does_not_accumulate_receivers_or_change_payload(self):
        m.export_handoff(self.cap, self.root/'first')
        first = self.root/'first'/self.cap.name
        m.export_handoff(first, self.root/'second')
        second = self.root/'second'/self.cap.name
        self.assertEqual(first.read_bytes(), second.read_bytes())
        legacy_total = self.cap.stat().st_size + len(m.recovery_handoff(
            m.file_sha256(self.cap), 2, self.cap.stat().st_size, 25_000_000))
        self.assertLess(first.stat().st_size, legacy_total)
        self.assertEqual(m.full_verify(str(first))['capsule_hash'],
                         m.full_verify(str(self.cap))['capsule_hash'])

    def test_corrupt_project_fails_before_publication(self):
        cold = self.cold()
        self.bootstrap(cold)
        path = cold/'input.cpc.md'
        data = path.read_bytes()
        start = data.index(b'<CPC>\n') + len(b'<CPC>\n')
        path.write_bytes(data[:start] + b'!' + data[start+1:])
        self.run_tool(cold/'cpc-tools/cpc-recover.py', cold,
                      'restore', 'input.cpc.md', '-o', 'restored', ok=False)
        self.assertFalse((cold/'restored').exists())
        self.assertEqual(list(cold.glob('.cpc-restore-*')), [])

    def test_payload_change_with_same_content_identity_is_rejected(self):
        other = self.root/'other.cpc.md'
        path = self.source/'run.py'
        stamp = path.stat().st_mtime_ns + 10_000_000_000
        os.utime(path, ns=(stamp, stamp))
        m.pack(str(self.source), str(other), archive_mode=True, file_exec={'run.py': True})
        self.assertEqual(m.full_verify(str(other))['content_id'],
                         m.full_verify(str(self.cap))['content_id'])
        original = m.decode_carrier
        reads = 0

        def change_between_reads(source, packed, strict_header=False):
            nonlocal reads
            if getattr(source, 'name', None) == str(self.cap):
                reads += 1
                if reads == 2:
                    self.cap.write_bytes(other.read_bytes())
            return original(source, packed, strict_header)

        with patch.object(m, 'decode_carrier', side_effect=change_between_reads):
            with self.assertRaisesRegex(m.CPCError, 'SOURCE_CHANGED'):
                m.export_handoff(self.cap, self.root/'changed')
        self.assertFalse((self.root/'changed').exists())

    def test_receiver_corruption_and_limits_fail_closed(self):
        cold = self.cold()
        path = cold/'input.cpc.md'
        original = path.read_bytes()
        marker = b'<!-- CPC-RECEIVER|1|b64>xz|'
        start = original.index(marker)
        header_end = original.index(b'\n', start)
        variants = {
            'hash': original[:start+len(marker)] + b'0'*64 + original[start+len(marker)+64:],
            'size': original[:header_end].rsplit(b'|', 1)[0]+b'|1048577'+original[header_end:],
            'truncated': original[:-30],
            'duplicate': original[:start]+original[start:]+original[start:],
        }
        for name, data in variants.items():
            with self.subTest(name=name):
                path.write_bytes(data)
                self.bootstrap(cold, ok=False)
                self.assertFalse((cold/'cpc-tools').exists())

    def test_receiver_rejects_trailing_stream_and_bounded_output(self):
        cold = self.cold()
        path = cold/'input.cpc.md'
        original = path.read_bytes()
        marker = b'<!-- CPC-RECEIVER|1|b64>xz|'
        start = original.index(marker)
        source = b'print("not executed")\n'
        for packed, declared in ((lzma.compress(source)+lzma.compress(b'extra'), len(source)),
                                 (lzma.compress(b'x'*2_000_000), 1)):
            footer = (marker+hashlib.sha256(source).hexdigest().encode()+b'|'
                      +str(declared).encode()+b'\n'+base64.b64encode(packed)
                      +b'\nCPC-RECEIVER-END -->\n')
            path.write_bytes(original[:start]+footer)
            self.bootstrap(cold, ok=False)
            self.assertFalse((cold/'cpc-tools').exists())

    def test_bootstrap_only_writes_source_and_never_overwrites(self):
        cold = self.cold()
        path = cold/'input.cpc.md'
        data = path.read_bytes()
        source = b'from pathlib import Path\nPath("EXECUTED").touch()\n'
        packed = base64.b64encode(lzma.compress(source))
        marker = b'<!-- CPC-RECEIVER|1|b64>xz|'
        footer = (marker+hashlib.sha256(source).hexdigest().encode()+b'|'
                  +str(len(source)).encode()+b'\n'+packed+b'\nCPC-RECEIVER-END -->\n')
        path.write_bytes(data[:data.index(marker)]+footer)
        self.bootstrap(cold)
        self.assertFalse((cold/'EXECUTED').exists())
        self.assertEqual((cold/'cpc-tools/cpc-recover.py').read_bytes(), source)
        self.bootstrap(cold, ok=False)
        self.assertEqual((cold/'cpc-tools/cpc-recover.py').read_bytes(), source)

    def test_readback_failure_and_existing_destination_preserve_work(self):
        with patch.object(m, 'compare', return_value=([], [], ['bad'], [])):
            with self.assertRaisesRegex(m.CPCError, 'RESTORE_COMPARE_FAILED'):
                m.restore_session(self.cap, self.root/'bad')
        self.assertFalse((self.root/'bad').exists())
        out = self.root/'existing'
        out.mkdir()
        (out/'keep').write_bytes(b'important')
        with self.assertRaisesRegex(m.CPCError, 'DEST_EXISTS'):
            m.restore_session(self.cap, out)
        self.assertEqual((out/'keep').read_bytes(), b'important')

    def test_file_capsule_receipt_has_no_name_collision(self):
        source = self.root/'RESTORE.json'
        source.write_bytes(b'opaque original data')
        cap = self.root/'file.cpc.md'
        m.pack(str(source), str(cap))
        receipt = m.restore_session(cap, self.root/'restored-file')
        self.assertEqual(Path(receipt['workspace']).read_bytes(), source.read_bytes())
        self.assertEqual(receipt['files'], 1)

    def test_wrapper_limit_uses_valid_parts_without_duplicating_receiver(self):
        # The bare capsule fits, but the capsule plus receiver does not.
        size = len(m.compact_guide(multipart=True, identity=m.file_sha256(self.cap), count=2)
                   +m.receiver_footer()) + 100
        result = m.export_handoff(self.cap, self.root/'parts', size)
        self.assertTrue(result['split'])
        paths = sorted((self.root/'parts').glob('*.cpcpart.md'))
        self.assertEqual(len(paths), 2)
        self.assertTrue(all(p.stat().st_size <= size for p in (self.root/'parts').iterdir()))
        self.assertIn(b'CPC-RECEIVER|1|', (self.root/'parts/HANDOFF.md').read_bytes())
        joined = self.root/'joined.cpc.md'
        m.join_parts(paths, joined)
        self.assertEqual(joined.read_bytes(), self.cap.read_bytes())
        cold = self.root/'multipart-cold'
        cold.mkdir()
        shutil.copytree(self.root/'parts', cold/'attachments')
        guide = (cold/'attachments/HANDOFF.md').read_text(encoding='utf-8')
        self.assertIn(result['set_sha256'], guide)
        script = guide.split('```python\n', 1)[1].split('```', 1)[0]
        (cold/'cpc-bootstrap.py').write_text(script, encoding='utf-8')
        self.run_tool(cold/'cpc-bootstrap.py', cold, 'attachments/HANDOFF.md')
        cli = cold/'cpc-tools/cpc-recover.py'
        self.run_tool(cli, cold, 'join', 'attachments', '-o', 'input.cpc.md')
        self.run_tool(cli, cold, 'restore', 'input.cpc.md', '-o', 'restored')
        receipt = json.loads((cold/'restored/RESTORE.json').read_text())
        self.assertEqual(m.compare(str(self.cap), receipt['workspace'])[:3], ([], [], []))
        with self.assertRaisesRegex(m.CPCError, 'HANDOFF_LIMIT'):
            m.export_handoff(self.cap, self.root/'too-small', 4096)
        self.assertFalse((self.root/'too-small').exists())

    def test_cli_defaults_to_self_contained_and_bare_remains_available(self):
        cli = ROOT/'bin/cpc.py'
        self.run_tool(cli, self.root, 'export', self.cap, '-o', 'complete')
        self.assertIn(b'CPC-RECEIVER|1|', (self.root/'complete'/self.cap.name).read_bytes())
        self.run_tool(cli, self.root, 'export', self.cap, '-o', 'bare', '--bare')
        self.assertEqual((self.root/'bare'/self.cap.name).read_bytes(), self.cap.read_bytes())
        self.run_tool(cli, self.root, 'v', self.cap, '--bare', ok=False)
        self.run_tool(cli, self.root, 'restore', self.cap, '-o', 'wrong',
                      '--expect-sha256', '0'*64, ok=False)
        self.assertFalse((self.root/'wrong').exists())


if __name__ == '__main__':
    unittest.main()
