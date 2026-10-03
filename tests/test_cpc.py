#!/usr/bin/env python3
# Copyright 2026 RioPlay
# SPDX-License-Identifier: MIT
import base64
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
CPC = HERE.parent / "bin" / "cpc.py"

def run(*args, cwd=None, expect=0, env=None):
    p = subprocess.run(
        [sys.executable, str(CPC), *map(str,args)],
        cwd=cwd, text=True, capture_output=True, env=env
    )
    if p.returncode != expect:
        raise AssertionError(
            f"cmd={args}\nexpected={expect} got={p.returncode}\nSTDOUT:\n{p.stdout}\nSTDERR:\n{p.stderr}"
        )
    return p

def tree_bytes(root):
    root = Path(root)
    out = {}
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root).as_posix()
        if p.is_file():
            out[("f", rel)] = p.read_bytes()
        elif p.is_dir():
            out[("d", rel)] = b""
    return out

def main():
    td = Path(tempfile.mkdtemp(prefix="cpc-test-"))
    try:
        src = td / "Project"
        src.mkdir()
        (src / "src").mkdir()
        (src / "empty").mkdir()
        (src / "src" / "main.py").write_bytes(b'print("hello")\r\n')
        (src / "README.md").write_text("# Demo\n", encoding="utf-8")
        (src / "blob.bin").write_bytes(bytes(range(256)) * 4)
        (src / ".DS_Store").write_bytes(b"trash")
        (src / "__pycache__").mkdir()
        (src / "__pycache__" / "x.pyc").write_bytes(b"trash")

        # pack
        cap = td / "Project.cpc.md"
        run("p", src, "-o", cap)
        assert cap.exists()
        raw1 = cap.read_bytes()

        # deterministic same runtime
        cap2 = td / "Project2.cpc.md"
        run(src, "-o", cap2,
            env=dict(os.environ, PYTHONIOENCODING="cp1252"))
        assert cap2.read_bytes() == raw1, "same-runtime pack not byte deterministic"

        # verify/list/inspect
        run("v", cap)
        lp = run("l", cap)
        assert "Project/src/main.py" in lp.stdout
        assert ".DS_Store" not in lp.stdout
        run("i", cap)

        # unpack
        outparent = td / "out"
        outparent.mkdir()
        run("u", cap, "-o", outparent)
        recovered = outparent / "Project"
        assert recovered.exists()
        assert (recovered / "src" / "main.py").read_bytes() == b'print("hello")\r\n'
        assert not (recovered / ".DS_Store").exists()

        # The short auto-detect workflow must behave like explicit unpack.
        automatic = td / "automatic"
        run(cap, "-o", automatic)
        assert tree_bytes(automatic / "Project") == tree_bytes(recovered)

        # compare equal
        run("c", cap, recovered)

        # modify then compare differs
        (recovered / "README.md").write_text("# Changed\n", encoding="utf-8")
        cp = run("c", cap, recovered, expect=1)
        assert "CHANGED" in cp.stdout

        # repack via sidecar; source capsule is original, so use explicit output
        cap3 = td / "Changed.cpc.md"
        run("r", recovered, "-o", cap3)
        run("v", cap3)

        # unpack changed, confirm bytes
        out2 = td / "out2"
        out2.mkdir()
        run("u", cap3, "-o", out2)
        assert (out2 / "Project" / "README.md").read_text(encoding="utf-8") == "# Changed\n"

        # A ZIP is auto-packed intact, not expanded or rewritten.
        one = td / "archive.zip"
        with zipfile.ZipFile(one, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("nested/file.bin", os.urandom(4096))
        onecap = td / "archive.zip.cpc.md"
        run(one, "-o", onecap)
        oneout = td / "oneout"
        oneout.mkdir()
        run("u", onecap, "-o", oneout)
        assert (oneout / "archive.zip").read_bytes() == one.read_bytes()

        # A normal file uses the same auto-pack / auto-unpack workflow.
        blobcap = td / "blob.cpc.md"
        run(src / "blob.bin", "-o", blobcap)
        run(blobcap, "-o", td / "blobout")
        assert (td / "blobout" / "blob.bin").read_bytes() == (src / "blob.bin").read_bytes()

        # outer rename does not matter
        renamed = td / "whatever.md"
        shutil.copy2(onecap, renamed)
        run("v", renamed)
        run(renamed, "-o", td / "renamedout")
        assert (td / "renamedout" / "archive.zip").read_bytes() == one.read_bytes()

        # corruption is rejected
        corrupt = td / "corrupt.cpc.md"
        text = onecap.read_text(encoding="utf-8")
        a = text.index("<CPC>") + len("<CPC>")
        b = text.index("</CPC>")
        payload = "".join(text[a:b].split())
        repl = ("A" if payload[0] != "A" else "B") + payload[1:]
        corrupt.write_text(text[:a] + "\n" + repl + "\n" + text[b:], encoding="utf-8")
        run("v", corrupt, expect=2)
        run(corrupt, "-o", td / "corruptout", expect=2)
        assert not (td / "corruptout").exists(), "corrupt capsule must not be auto-packed"

        # overwrite default rejects
        run("p", src, "-o", cap, expect=2)
        run("p", src, "-o", cap, "-f")

        # include override + archive lossless-for-supported-files
        inc = td / "IncludeTest"
        inc.mkdir()
        (inc / "__pycache__").mkdir()
        (inc / "__pycache__" / "keep.pyc").write_bytes(b"KEEP")
        (inc / "main.py").write_text("print(1)\n", encoding="utf-8")
        inc_default = td / "inc-default.cpc.md"
        inc_forced = td / "inc-forced.cpc.md"
        inc_archive = td / "inc-archive.cpc.md"
        run("p", inc, "-o", inc_default)
        run("p", inc, "--include", "__pycache__/*", "-o", inc_forced)
        run("p", inc, "-a", "-o", inc_archive)
        assert "keep.pyc" not in run("l", inc_default).stdout
        assert "keep.pyc" in run("l", inc_forced).stdout
        assert "keep.pyc" in run("l", inc_archive).stdout

        # .cpcignore is chat-only and can be overridden by --include
        (inc / ".cpcignore").write_text("main.py\n", encoding="utf-8")
        ignored = td / "ignored.cpc.md"
        restored = td / "restored.cpc.md"
        archive_ignores_policy = td / "archive-policy.cpc.md"
        run("p", inc, "-o", ignored)
        run("p", inc, "--include", "main.py", "-o", restored)
        run("p", inc, "-a", "-o", archive_ignores_policy)
        assert "main.py" not in run("l", ignored).stdout
        assert "main.py" in run("l", restored).stdout
        assert "main.py" in run("l", archive_ignores_policy).stdout

        # portable-name/case collision
        bad = td / "Bad"
        bad.mkdir()
        (bad / "Foo.txt").write_text("a", encoding="utf-8")
        (bad / "foo.txt").write_text("b", encoding="utf-8")
        if len(list(bad.iterdir())) == 2:
            run("p", bad, "-o", td/"bad.cpc.md", expect=2)

        # Exercise collision rejection even on case-insensitive filesystems,
        # where the second write above replaces the first file.
        spec = importlib.util.spec_from_file_location("cpc", CPC)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with patch.object(module.os, "walk", return_value=[
            (str(bad), [], ["Foo.txt", "foo.txt"])
        ]):
            try:
                module.walk_input(str(bad))
            except module.CPCError as error:
                assert "CASE_COLLISION" in str(error), str(error)
            else:
                raise AssertionError("case collision was not rejected")

        print("ALL CPC POC TESTS PASSED")
    finally:
        shutil.rmtree(td, ignore_errors=True)

if __name__ == "__main__":
    main()
