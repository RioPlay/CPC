#!/usr/bin/env python3
# Copyright 2026 RioPlay
# SPDX-License-Identifier: MIT
import argparse, os, shutil, stat, sys
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
    print("CPC installed:", launch)
    print("Add to PATH if needed:", bindir)

def uninstall(prefix=None):
    bindir = Path(prefix).expanduser().resolve() if prefix else default_bin_dir()
    for n in ("cpc.py","cpc","cpc.cmd"):
        p=bindir/n
        if p.exists(): p.unlink()
    print("CPC uninstalled from", bindir)

p=argparse.ArgumentParser()
p.add_argument("--prefix")
p.add_argument("--uninstall", action="store_true")
ns=p.parse_args()
uninstall(ns.prefix) if ns.uninstall else install(ns.prefix)
