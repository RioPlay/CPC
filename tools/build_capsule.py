#!/usr/bin/env python3
# Copyright 2026 RioPlay
# SPDX-License-Identifier: MIT
"""Build or check the public CPC capsule using an explicit file allowlist."""
import argparse
import importlib.util
import os
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    ".cpcignore", ".gitattributes", ".gitignore",
    ".github/workflows/ci.yml",
    "README.md", "FAQ.md", "ROADMAP.md", "CONTRIBUTING.md", "GOVERNANCE.md",
    "LICENSE", "PROJECT.json", "SECURITY.md", "TRANSFER_VALIDATION.md",
    "bin/cpc.py", "bootstrap.py", "install.ps1", "install.sh",
    "demo_project/README.md", "demo_project.cpc.md",
    "standard/README.md", "standard/SPEC.md", "standard/CONFORMANCE.md",
    "standard/CLI_PROFILE.md", "standard/SECURITY.md",
    "standard/STANDARD.json", "standard/TEST_VECTOR.md",
    "standard/test-vector.cpc.md", "tests/test_cpc.py", "tests/test_security.py",
    "tests/test_streaming.py", "tests/test_export.py", "tests/test_timestamps.py",
    "tests/test_recovery.py", "tests/test_basic.py", "tests/test_headers.py",
    "tests/test_build_capsule.py", "tests/test_transfer.py", "tests/test_handoff.py", "tools/build_capsule.py", "tools/measure_sizes.py",
    "tools/profile_resources.py",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="verify the existing capsule, allowed file set, and source bytes")
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("cpc", ROOT / "bin/cpc.py")
    cpc = importlib.util.module_from_spec(spec)
    # A read-only check must not create or refresh source-tree bytecode caches.
    previous_bytecode_policy = sys.dont_write_bytecode
    try:
        if args.check:
            sys.dont_write_bytecode = True
        spec.loader.exec_module(cpc)
    finally:
        sys.dont_write_bytecode = previous_bytecode_policy
    output = ROOT / "CPC.cpc.md"
    if not args.check:
        with tempfile.TemporaryDirectory(prefix="cpc-release-") as tmp:
            stage = Path(tmp) / "CPC"
            for name in FILES:
                source = ROOT / name
                if not source.is_file() or source.is_symlink():
                    raise RuntimeError(f"Missing or unsupported release file: {name}")
                target = stage / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                target.chmod(0o755 if name in (
                    "bin/cpc.py", "bootstrap.py", "install.sh"
                ) else 0o644)
            # This is an allowlisted release tree, not a copy of every source
            # directory. Derive its synthetic directory dates from included
            # files, so staging time and the previous self-capsule do not leak in.
            directories = [stage] + [p for p in stage.rglob("*") if p.is_dir()]
            for directory in sorted(directories, key=lambda p: len(p.parts), reverse=True):
                ns = max(p.stat().st_mtime_ns for p in directory.iterdir())
                os.utime(directory, ns=(ns, ns))
            bare = Path(tmp)/"bare"/"CPC.cpc.md"
            cpc.pack(str(stage), output=str(bare))
            exported = Path(tmp)/"export"
            cpc.export_handoff(bare, exported)
            cpc.atomic_write(str(output), (exported/"CPC.cpc.md").read_bytes(), force=True)
    info = cpc.full_verify(str(output))
    expected = {"CPC/" + name for name in FILES}
    actual = {name for name, record in info["manifest"].items()
              if record[0] == "f"}
    if actual != expected:
        raise RuntimeError(f"Release file mismatch: extra={sorted(actual - expected)}, "
                           f"missing={sorted(expected - actual)}")
    mismatched = []
    for name in sorted(FILES):
        source = ROOT / name
        if not source.is_file() or source.is_symlink():
            raise RuntimeError(f"Missing or unsupported release file: {name}")
        record = info["manifest"]["CPC/" + name]
        # full_verify has checked these hashes against the archived bytes.
        # Source dates and executable bits are not release-content differences.
        if source.stat().st_size != record[1] or cpc.file_sha256(source) != record[3]:
            mismatched.append(name)
    if mismatched:
        raise RuntimeError(f"Release content mismatch: {mismatched}")
    if not output.read_bytes().endswith(cpc.receiver_footer()):
        raise RuntimeError("Release receiver mismatch: rebuild the self-contained capsule")
    print(f"CPC release capsule verified: {len(actual)} files, "
          f"{output.stat().st_size} bytes")


if __name__ == "__main__":
    main()
