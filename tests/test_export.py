#!/usr/bin/env python3
# Copyright 2026 RioPlay
# SPDX-License-Identifier: MIT
import hashlib
import json
from pathlib import Path
import random
import shutil
import tempfile
import unittest
import subprocess
import sys
import os
from unittest.mock import patch
import importlib.util
import io
from contextlib import redirect_stdout, redirect_stderr

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("cpc", ROOT / "bin/cpc.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class MultipartTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix='cpc-multipart-test-')
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        source=self.root/'Project'
        source.mkdir()
        (source/'empty').mkdir()
        (source/'source.bin').write_bytes(random.Random(0).randbytes(300000))
        self.cap=self.root/'Project.cpc.md'
        m.pack(str(source),str(self.cap),preset=0)

    def parts(self):
        folder=self.root/'parts'
        result=m.export_capsule(self.cap,folder,131072)
        parts=sorted(folder.glob('*.cpcpart.md'))
        self.assertGreater(len(parts),1)
        self.assertTrue(all(p.stat().st_size<=131072 for p in folder.iterdir()))
        return parts,result

    def rejected(self,parts,reason):
        out=self.root/'joined.cpc.md'
        with self.assertRaisesRegex(m.CPCError,reason): m.join_parts(parts,out)
        self.assertFalse(out.exists())
        self.assertEqual(list(self.root.glob('.cpc-join-*')),[])

    def test_default_and_size_units(self):
        self.assertEqual(m.DEFAULT_EXPORT_LIMIT,25_000_000)
        self.assertEqual(m.parse_export_size('25MB'),25_000_000)
        self.assertEqual(m.parse_export_size('25MiB'),26_214_400)
        for value in ('-1','0','10.5MB','banana'):
            with self.assertRaises(Exception): m.parse_export_size(value)
        result=m.export_capsule(self.cap,self.root/'whole')
        self.assertFalse(result['split'])
        self.assertEqual(list((self.root/'whole').iterdir()),[self.root/'whole'/self.cap.name])
        self.assertEqual((self.root/'whole'/self.cap.name).read_bytes(),self.cap.read_bytes())

    def test_exact_boundary_and_one_byte_over(self):
        size=self.cap.stat().st_size
        self.assertFalse(m.export_capsule(self.cap,self.root/'exact',size)['split'])
        self.assertTrue(m.export_capsule(self.cap,self.root/'over',size-1)['split'])
        self.assertTrue(all(p.stat().st_size<=size-1 for p in (self.root/'over').iterdir()))

    def test_order_names_and_exact_restore(self):
        parts,_=self.parts()
        for i,p in enumerate(parts): p.rename(p.with_name(str(i)+'.md'))
        parts=list((self.root/'parts').glob('[0-9]*.md'))
        out=self.root/'joined.cpc.md'
        m.join_parts(list(reversed(parts)),out)
        self.assertEqual(out.read_bytes(),self.cap.read_bytes())
        restored,_,_=m.unpack(str(out),str(self.root/'restored'))
        self.assertTrue((Path(restored)/'empty').is_dir())
        self.assertEqual((Path(restored)/'source.bin').read_bytes(),(self.root/'Project/source.bin').read_bytes())

    def test_missing_duplicate_and_mixed(self):
        parts,_=self.parts()
        self.rejected(parts[:-1],'MISSING_PART')
        self.rejected(parts+[parts[0]],'DUPLICATE_PART')
        data=parts[0].read_bytes()
        parts[0].write_bytes(data.replace(data.split(b'|')[2],b'f'*64,1))
        self.rejected(parts,'MIXED_SET')

    def test_truncated_and_corrupted(self):
        parts,_=self.parts()
        original=parts[0].read_bytes()
        parts[0].write_bytes(original[:-1])
        self.rejected(parts,'PART_HASH_MISMATCH')
        parts[0].write_bytes(original[:m.PART_HEADER_SIZE]+b'!'+original[m.PART_HEADER_SIZE+1:])
        self.rejected(parts,'PART_HASH_MISMATCH')

    def test_forged_part_hash_does_not_bypass_set_hash(self):
        parts,_=self.parts()
        original=parts[0].read_bytes()
        match=m.PART_PATTERN.fullmatch(original[:m.PART_HEADER_SIZE])
        identity,index,count,size,_=match.groups()
        body=b'!'+original[m.PART_HEADER_SIZE+1:]
        parts[0].write_bytes(m.part_header(identity.decode(),int(index),int(count),int(size),hashlib.sha256(body).hexdigest())+body)
        self.rejected(parts,'SET_HASH_MISMATCH')

    def test_limits_before_body_reads(self):
        parts,_=self.parts()
        data=parts[0].read_bytes()
        fields=data[:m.PART_HEADER_SIZE].split(b'|')
        fields[5]=f'{m.MAX_CARRIER+1:020d}'.encode()
        parts[0].write_bytes(b'|'.join(fields)+data[m.PART_HEADER_SIZE:])
        self.rejected(parts,'PART_LIMIT')
        with patch.object(m,'MAX_PARTS',2):
            with self.assertRaisesRegex(m.CPCError,'PART_COUNT_LIMIT'):
                m.export_capsule(self.cap,self.root/'too-many',1024)
        self.assertFalse((self.root/'too-many').exists())

    def test_existing_output_and_failed_export(self):
        parts,_=self.parts()
        out=self.root/'existing.cpc.md'
        out.write_bytes(b'original')
        with self.assertRaisesRegex(m.CPCError,'DEST_EXISTS'): m.join_parts(parts,out)
        self.assertEqual(out.read_bytes(),b'original')
        with self.assertRaisesRegex(m.CPCError,'DEST_EXISTS'):
            m.export_capsule(self.cap,self.root/'parts',131072)
        with patch.object(m,'join_parts',side_effect=OSError('simulated disk full')):
            with self.assertRaises(OSError): m.export_capsule(self.cap,self.root/'failed',131072)
        self.assertFalse((self.root/'failed').exists())
        self.assertEqual(list(self.root.glob('.cpc-export-*')),[])

    def test_cli_export_join_and_part_detection(self):
        exported = self.root / 'cli-export'
        joined = self.root / 'cli-joined.cpc.md'
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(m.main(['export', str(self.cap), '-o', str(exported),
                                     '--max-file-size', '128KiB']), 0)
            self.assertEqual(m.main(['join', str(exported), '-o', str(joined)]), 0)
            part = next(exported.glob('*.cpcpart.md'))
            self.assertEqual(m.main([str(part)]), 2)
            self.assertEqual(m.main(['u', str(part)]), 2)
            self.assertEqual(m.main(['p', str(self.root/'Project'), '--max-file-size', '25MB']), 2)
            self.assertEqual(m.main(['export', str(self.cap), '-o', str(exported), '-f']), 2)
        self.assertEqual(joined.read_bytes(), self.cap.read_bytes())
        self.assertFalse(Path(str(part)+'.cpc.md').exists())

    def test_export_source_and_selection(self):
        source = self.root / 'Project'
        (source/'omit.txt').write_bytes(b'omit me')
        result = m.export_project(source, self.root/'selected', excludes=['omit.txt'])
        self.assertFalse(result['split'])
        cap = next((self.root/'selected').glob('*.cpc.md'))
        manifest = m.full_verify(str(cap))['manifest']
        self.assertNotIn('Project/omit.txt', manifest)
        self.assertIn('Project/empty', manifest)
        with self.assertRaisesRegex(m.CPCError, 'EXPORT_INSIDE_SOURCE'):
            m.export_project(source, source/'exports')
        with self.assertRaisesRegex(m.CPCError, 'EXPORT_CAPSULE_OPTIONS'):
            m.export_project(self.cap, self.root/'ignored-options', excludes=['omit.txt'])

    def test_default_compression_and_repack(self):
        source = self.root / 'Project'
        default, explicit = self.root/'default.cpc.md', self.root/'six.cpc.md'
        result = m.pack(str(source), str(default))
        self.assertEqual(result['preset'], 6)
        m.pack(str(source), str(explicit), preset=6)
        self.assertEqual(default.read_bytes(), explicit.read_bytes())
        with redirect_stdout(io.StringIO()):
            cli = self.root/'cli.cpc.md'
            self.assertEqual(m.main([str(source), '-o', str(cli)]), 0)
        self.assertEqual(cli.read_bytes(), explicit.read_bytes())
        restored, _, _ = m.unpack(str(default), str(self.root/'restored'))
        result = m.repack(restored, str(self.root/'repacked.cpc.md'))
        self.assertEqual(result['preset'], 6)

    def test_part_hashes_do_not_replace_archive_validation(self):
        data = b'not a CPC archive'
        identity = hashlib.sha256(data).hexdigest()
        parts = []
        for index, body in enumerate((data[:5], data[5:]), 1):
            part = self.root / (str(index)+'.cpcpart.md')
            part.write_bytes(m.part_header(identity, index, 2, len(data),
                                           hashlib.sha256(body).hexdigest())+body)
            parts.append(part)
        out = self.root/'invalid.cpc.md'
        with self.assertRaises(m.CPCError):
            m.join_parts(parts, out)
        self.assertFalse(out.exists())

    def test_handoff_restores_without_installed_cpc_or_repository(self):
        source = self.root/'Project'
        (source/'run.sh').write_bytes(b'#!/bin/sh\necho PROJECT_CODE_MUST_NOT_RUN\n')
        m.pack(str(source), str(self.cap), force=True, preset=0,
               file_exec={'run.sh': True, 'source.bin': False})
        parts, result = self.parts()
        handoff = (self.root/'parts/HANDOFF.md').read_text(encoding='utf-8')
        self.assertIn(result['set_sha256'], handoff)
        self.assertIn(f"Required numbered parts: {len(parts)}", handoff)
        self.assertIn('No CPC installation', handoff)
        receiver = handoff.split('````python\n', 1)[1].rsplit('````', 1)[0]
        # The guide carries the actual standalone implementation, not another decoder.
        self.assertEqual(receiver, (ROOT/'bin/cpc.py').read_text(encoding='utf-8').rstrip('\n')+'\n')
        for scenario in ('complete', 'missing', 'corrupt'):
            with self.subTest(scenario=scenario):
                cold = self.root/scenario
                cold.mkdir()
                attachments = cold/'attachments'
                shutil.copytree(self.root/'parts', attachments)
                (cold/'cpc-recover.py').write_text(receiver, encoding='utf-8')
                copied = sorted(attachments.glob('*.cpcpart.md'))
                if scenario == 'missing':
                    copied[-1].unlink()
                elif scenario == 'corrupt':
                    with copied[0].open('r+b') as f:
                        f.seek(m.PART_HEADER_SIZE)
                        f.write(b'!')
                # -I excludes the repository, script directory and PYTHONPATH from imports.
                joined = subprocess.run(
                    [sys.executable, '-I', 'cpc-recover.py', 'join', './attachments',
                     '-o', './reconstructed.cpc.md'], cwd=cold,
                    capture_output=True, text=True, timeout=30)
                if scenario != 'complete':
                    self.assertEqual(joined.returncode, 2, joined.stderr)
                    self.assertIn('MISSING_PART' if scenario == 'missing' else 'PART_HASH_MISMATCH', joined.stderr)
                    self.assertFalse((cold/'reconstructed.cpc.md').exists())
                    self.assertFalse((cold/'recovered').exists())
                    continue
                self.assertEqual(joined.returncode, 0, joined.stderr)
                self.assertEqual((cold/'reconstructed.cpc.md').read_bytes(), self.cap.read_bytes())
                restored = subprocess.run(
                    [sys.executable, '-I', 'cpc-recover.py', 'u', './reconstructed.cpc.md',
                     '-o', './recovered'], cwd=cold,
                    capture_output=True, text=True, timeout=30)
                self.assertEqual(restored.returncode, 0, restored.stderr)
                self.assertNotIn('PROJECT_CODE_MUST_NOT_RUN', restored.stdout)
                tree = cold/'recovered/Project'
                self.assertTrue((tree/'empty').is_dir())
                for path in source.iterdir():
                    if path.is_file():
                        self.assertEqual((tree/path.name).read_bytes(), path.read_bytes())
                        self.assertEqual((tree/path.name).stat().st_mtime_ns, path.stat().st_mtime_ns)
                _, state = m.read_sidecar_for(str(tree))
                self.assertTrue(m.recorded_executable_intent(state)['run.sh'])
                if os.name != 'nt':
                    self.assertTrue((tree/'run.sh').stat().st_mode & 0o111)

    def test_too_small_limit_cannot_publish_an_unusable_handoff(self):
        with self.assertRaisesRegex(m.CPCError, 'HANDOFF_LIMIT'):
            m.export_capsule(self.cap, self.root/'too-small-guide', 4096)
        self.assertFalse((self.root/'too-small-guide').exists())
        self.assertEqual(list(self.root.glob('.cpc-export-*')), [])

    def test_cold_edit_return_roundtrip_and_missing_state(self):
        source = self.root/'Project'
        (source/'run.sh').write_bytes(b'#!/bin/sh\necho original\n')
        m.pack(str(source), str(self.cap), force=True, preset=0,
               file_exec={'run.sh': True, 'source.bin': False})
        for limit in (25_000_000, 131072):
            with self.subTest(limit=limit):
                cold = self.root/str(limit)
                cold.mkdir()
                attachments = cold/'attachments'
                result = m.export_capsule(self.cap, attachments, limit)
                # Single v1 capsules still need a separately supplied CLI. Exercise
                # that existing path without implying it is a self-contained handoff.
                if result['split']:
                    guide = (attachments/'HANDOFF.md').read_text(encoding='utf-8')
                else:
                    guide = m.recovery_handoff(result['set_sha256'], 1,
                                              result['original_bytes'], limit).decode('utf-8')
                receiver = guide.split('````python\n', 1)[1].rsplit('````', 1)[0]
                (cold/'cpc-recover.py').write_text(receiver, encoding='utf-8')

                def run(*args, expected=0):
                    result = subprocess.run(
                        [sys.executable, '-I', 'cpc-recover.py', *args], cwd=cold,
                        capture_output=True, text=True, timeout=30)
                    self.assertEqual(result.returncode, expected, result.stderr)
                    return result

                original = './input.cpc.md'
                if result['split']:
                    run('join', './attachments', '-o', original)
                else:
                    shutil.copyfile(attachments/self.cap.name, cold/'input.cpc.md')
                run('v', original)
                run('u', original, '-o', './recovered')
                tree = cold/'recovered/Project'
                (tree/'run.sh').write_bytes(b'#!/bin/sh\necho edited\n')
                (tree/'new.txt').write_bytes(b'new work\n')
                run('r', './recovered/Project', '-o', './updated.cpc.md')
                run('v', './updated.cpc.md')
                self.assertIn('CPC EQUAL', run('c', './updated.cpc.md', './recovered/Project').stdout)
                run('u', './updated.cpc.md', '-o', './return-check')
                run('export', './updated.cpc.md', '-o', './return-files',
                    '--max-file-size', str(limit))
                returned = cold/'return-files'
                self.assertEqual((returned/'HANDOFF.md').is_file(), result['split'])
                self.assertTrue(all(p.stat().st_size <= limit for p in returned.iterdir()))
                if result['split']:
                    run('join', './return-files', '-o', './returned.cpc.md')
                else:
                    shutil.copyfile(returned/'updated.cpc.md', cold/'returned.cpc.md')
                run('u', './returned.cpc.md', '-o', './next-sandbox')
                next_tree = cold/'next-sandbox/Project'
                for rel in ('source.bin', 'run.sh', 'new.txt'):
                    self.assertEqual((next_tree/rel).read_bytes(), (tree/rel).read_bytes())
                    self.assertEqual((next_tree/rel).stat().st_mtime_ns, (tree/rel).stat().st_mtime_ns)
                self.assertTrue((next_tree/'empty').is_dir())
                self.assertEqual((next_tree/'empty').stat().st_mtime_ns, (tree/'empty').stat().st_mtime_ns)
                _, state = m.read_sidecar_for(str(next_tree))
                self.assertTrue(m.recorded_executable_intent(state)['run.sh'])
                # Missing local metadata must not silently cause a fresh pack.
                (cold/'recovered/.Project.cpc-state').unlink()
                failed = run('r', './recovered/Project', '-o', './should-not-exist.cpc.md', expected=2)
                self.assertIn('STATE_NOT_FOUND', failed.stderr)
                self.assertIn('Keep the edited project intact', failed.stderr)
                self.assertFalse((cold/'should-not-exist.cpc.md').exists())
                self.assertEqual((tree/'new.txt').read_bytes(), b'new work\n')


if __name__=='__main__': unittest.main()
