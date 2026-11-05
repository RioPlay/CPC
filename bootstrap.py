#!/usr/bin/env python3
# Copyright 2026 RioPlay
# SPDX-License-Identifier: MIT
import argparse, hashlib, os, shutil, stat, subprocess, sys
from pathlib import Path

def default_bin_dir():
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home()/"AppData"/"Local")
        return Path(base)/"CPC"/"bin"
    return Path.home()/".local"/"bin"

def install(prefix=None):
    here = Path(__file__).resolve().parent
    src = here/"bin"/"cpc.py"
    bindir = Path(prefix).expanduser().resolve() if prefix else default_bin_dir()
    bindir.mkdir(parents=True, exist_ok=True)
    core = bindir/"cpc.py"
    shutil.copyfile(src, core)
    if os.name == "nt":
        launch = bindir/"cpc.cmd"
        launch.write_text('@echo off\r\n"' + sys.executable + '" "%~dp0cpc.py" %*\r\n', encoding="utf-8")
    else:
        launch = bindir/"cpc"
        launch.write_text("#!"+sys.executable+"\nimport runpy,sys\nsys.argv[0]="+repr(str(core))+"\nrunpy.run_path("+repr(str(core))+",run_name='__main__')\n", encoding="utf-8")
        launch.chmod(launch.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    if core.read_bytes() != src.read_bytes():
        raise RuntimeError("Installed CPC does not match the source file")
    version = subprocess.run([sys.executable, str(core), "--version"],
                             check=True, capture_output=True, text=True).stdout.strip()
    print("CPC installed:", launch)
    print("Source:", src)
    print("Installed version:", version)
    print("Installed SHA256:", hashlib.sha256(core.read_bytes()).hexdigest())
    active = shutil.which("cpc")
    if active and os.path.normcase(os.path.realpath(active)) == os.path.normcase(os.path.realpath(launch)):
        print("PATH selects this installation:", active)
    elif active:
        print("WARNING: PATH selects a different CPC:", active, file=sys.stderr)
        print("Put this directory before that copy in PATH:", bindir, file=sys.stderr)
    else:
        print("WARNING: cpc is not on PATH. Add this directory:", bindir, file=sys.stderr)
    if os.name == "nt":
        print("Check your current PowerShell session: Get-Command cpc -All")
    else:
        print("Refresh and check your current shell: hash -r; type cpc")
    print("Shell aliases or functions can also override PATH lookup.")
    return launch

def uninstall(prefix=None):
    bindir = Path(prefix).expanduser().resolve() if prefix else default_bin_dir()
    for n in ("cpc.py","cpc","cpc.cmd"):
        p=bindir/n
        if p.exists(): p.unlink()
    print("CPC uninstalled from", bindir)

def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--prefix")
    p.add_argument("--uninstall", action="store_true")
    ns=p.parse_args(argv)
    uninstall(ns.prefix) if ns.uninstall else install(ns.prefix)


if __name__ == "__main__":
    main()
