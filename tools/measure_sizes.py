#!/usr/bin/env python3
# Copyright 2026 RioPlay
# SPDX-License-Identifier: MIT
"""Measure CPC source packaging with and without an already-compressed asset.

Fixtures are generated only in a temporary directory, never in the repository.
Results depend on source revision and the Python/LZMA runtime.
"""
import importlib.util
import os
from pathlib import Path
import random
import shutil
import tempfile
import zipfile

from build_capsule import FILES, ROOT


def main():
    spec = importlib.util.spec_from_file_location("cpc", ROOT / "bin/cpc.py")
    cpc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cpc)
    with tempfile.TemporaryDirectory(prefix="cpc-size-") as tmp:
        project = Path(tmp) / "Project"
        # Measure the runnable source and regression tests, independent of
        # documentation edits and nested demo capsules.
        for name in FILES:
            if name.endswith(".py") and not name.startswith("tools/"):
                target = project / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / name, target)
        for with_assets in (False, True):
            if with_assets:
                assets = project / "assets"
                assets.mkdir()
                rng = random.Random(0)
                data = bytes(rng.getrandbits(8) for _ in range(1024 * 1024))
                entry = zipfile.ZipInfo("opaque.bin", (2026, 1, 1, 0, 0, 0))
                entry.compress_type = zipfile.ZIP_DEFLATED
                with zipfile.ZipFile(assets / "bundle.zip", "w") as archive:
                    archive.writestr(entry, data)
                os.utime(assets / "bundle.zip", (1767225600, 1767225600))
            for directory in sorted([project]+[p for p in project.rglob("*") if p.is_dir()],
                                    key=lambda p: len(p.parts), reverse=True):
                ns = max(p.stat().st_mtime_ns for p in directory.iterdir())
                os.utime(directory, ns=(ns, ns))
            capsule = Path(tmp) / ("assets.cpc.md" if with_assets else "source.cpc.md")
            result = cpc.pack(str(project), output=str(capsule))
            before, after = result["source_bytes"], result["carrier_bytes"]
            label = "Source plus compressed asset" if with_assets else "CPC Python source and tests"
            print(f"{label}: {before:,} -> {after:,} bytes ({after / before:.1%} of input)")


if __name__ == "__main__":
    main()
