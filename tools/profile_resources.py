#!/usr/bin/env python3
# Copyright 2026 RioPlay
# SPDX-License-Identifier: MIT
"""Compare peak resident memory, elapsed time, and capsule size in fresh processes.

All generated corpora and capsules stay in a temporary directory. Optional JSON
results belong outside the release tree. A baseline must be trusted Python code.
"""
import argparse
import ctypes
import importlib.util
import json
import os
from pathlib import Path
import platform
import random
import subprocess
import sys
import tempfile
import time


def peak_rss():
    if os.name == "nt":
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD)] + [
                (name, ctypes.c_size_t) for name in (
                    "peak", "working", "peak_paged", "paged", "peak_nonpaged",
                    "nonpaged", "pagefile", "peak_pagefile")]
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            raise ctypes.WinError(ctypes.get_last_error())
        return counters.peak
    import resource
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak if sys.platform == "darwin" else peak * 1024


def worker(module, operation, source, target, preset):
    spec = importlib.util.spec_from_file_location("cpc", module)
    cpc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cpc)
    started = time.perf_counter()
    if operation == "pack":
        cpc.pack(source, output=target, preset=int(preset))
        size = Path(target).stat().st_size
    else:
        cpc.unpack(source, output=target)
        size = Path(source).stat().st_size
    print(json.dumps({"seconds": time.perf_counter() - started,
                      "peak_rss_bytes": peak_rss(), "capsule_bytes": size}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--sizes", type=int, nargs="+", default=[8, 32])
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.repeats < 1 or any(size < 1 for size in args.sizes):
        parser.error("sizes and repeats must be positive")
    implementations = {"streaming": Path(__file__).resolve().parents[1] / "bin/cpc.py"}
    if args.baseline:
        implementations["buffered"] = args.baseline.resolve()
    rows = []
    with tempfile.TemporaryDirectory(prefix="cpc-profile-") as tmp:
        root = Path(tmp)
        for size in args.sizes:
            for corpus in ("text", "binary"):
                project = root / f"{corpus}-{size}"
                project.mkdir()
                rng = random.Random(0)
                text = b"".join(
                    f"2026-01-01 INFO job={i} module=worker status=complete duration={i % 97}ms\n".encode()
                    for i in range(16000))[:1024 * 1024]
                with (project / ("events.log" if corpus == "text" else "assets.bin")).open("wb") as out:
                    for _ in range(size):
                        out.write(text if corpus == "text" else rng.randbytes(1024 * 1024))
                for preset in (6, 9):
                    for repeat in range(args.repeats):
                        # Alternate order to reduce systematic cache/order bias.
                        names = list(implementations)
                        if repeat % 2:
                            names.reverse()
                        for name in names:
                            capsule = root / f"{corpus}-{size}-{preset}-{repeat}-{name}.cpc.md"
                            for operation in ("pack", "unpack"):
                                source = project if operation == "pack" else capsule
                                target = capsule if operation == "pack" else capsule.with_suffix(".out")
                                result = subprocess.run(
                                    [sys.executable, __file__, "--worker", str(implementations[name]),
                                     operation, str(source), str(target), str(preset)],
                                    check=True, text=True, capture_output=True)
                                row = dict(json.loads(result.stdout), implementation=name,
                                           operation=operation, corpus=corpus, size_mib=size,
                                           preset=preset, repeat=repeat,
                                           input_bytes=sum(p.stat().st_size for p in project.iterdir()))
                                rows.append(row)
                                print(json.dumps(row), flush=True)
    if args.output:
        args.output.write_text(json.dumps({"python": sys.version, "platform": platform.platform(),
                                          "rows": rows}, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        worker(*sys.argv[2:])
    else:
        main()
