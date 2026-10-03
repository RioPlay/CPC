#!/usr/bin/env python3
# Copyright 2026 RioPlay
# SPDX-License-Identifier: MIT
"""
CPC reference implementation 0.3.0-rc.6

Primary workflow:
    cpc.py                  # pack current directory
    cpc.py THING            # pack normal input / unpack CPC capsule
    cpc.py r PATH           # repack using CPC sidecar state
    cpc.py v CAPSULE        # verify
    cpc.py l CAPSULE        # list
    cpc.py i CAPSULE        # inspect
    cpc.py c CAPSULE PATH   # compare
    cpc.py x CAPSULE MEMBER # selective extract

Canonical minimal carrier:
    #CPC|1|b64>xz>tar|<sha256-of-xz>
    <CPC>
    BASE64
    </CPC>

The outer SHA-256 protects the XZ payload in transit. Deeper per-file
verification is provided by the manifest inside the compressed TAR.

Critical recovery primitives are Python-standard-library only:
base64, hashlib, lzma, tarfile.

The complete CLI uses additional standard-library helpers for filesystem,
staging, atomic replacement, and argument handling. No third-party package
is required.
"""

import argparse
import fnmatch
import base64
import hashlib
import io
import lzma
import os
import shutil
import sys
import tarfile
import tempfile

VERSION = "1"  # CPC wire-format version
RELEASE_VERSION = "0.3.0-rc.6"
CODEC = "xz"
START = "<CPC>"
END = "</CPC>"
META_ROOT = ".cpc"
STATE_NAME = "state"
MANIFEST_NAME = "manifest"

# Conservative default chat exclusions.
EXCLUDE_DIRS = {".git", "__pycache__"}
EXCLUDE_FILES = {".DS_Store", "Thumbs.db"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo"}

# Deliberately finite POC safety limits.
MAX_CARRIER = 512 * 1024 * 1024
MAX_COMPRESSED = 384 * 1024 * 1024
MAX_TAR = 2 * 1024 * 1024 * 1024
MAX_MEMBERS = 200_000
MAX_FILE = 1024 * 1024 * 1024
MAX_TOTAL = 2 * 1024 * 1024 * 1024
MAX_PATH = 1024
MAX_DEPTH = 100

WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

class CPCError(Exception):
    pass

def sha256(data):
    return hashlib.sha256(data).hexdigest()

def posix_rel(path):
    return path.replace(os.sep, "/")

def matches_any(rel, patterns):
    rel = rel.replace(os.sep, "/")
    name = rel.rsplit("/", 1)[-1]
    for pat in patterns or ():
        p = pat.replace(os.sep, "/")
        if fnmatch.fnmatchcase(rel, p) or fnmatch.fnmatchcase(name, p):
            return True
    return False

def is_excluded(rel, is_dir, archive_mode=False, includes=None, excludes=None, ignores=None):
    # Explicit command-line exclude is highest precedence.
    if matches_any(rel, excludes):
        return True
    # Explicit include overrides .cpcignore and built-in automatic ignores.
    if matches_any(rel, includes):
        return False
    if is_dir:
        prefix = rel.replace(os.sep, "/").rstrip("/") + "/"
        for pat in includes or ():
            p = pat.replace(os.sep, "/")
            if p.startswith(prefix):
                return False
    if matches_any(rel, ignores):
        return True
    if archive_mode:
        return False
    parts = rel.split("/")
    if any(p in EXCLUDE_DIRS for p in parts):
        return True
    name = parts[-1]
    if name in EXCLUDE_FILES:
        return True
    if not is_dir and any(name.endswith(s) for s in EXCLUDE_SUFFIXES):
        return True
    return False

def portable_name_check(rel):
    if not rel or rel.startswith("/") or "\x00" in rel:
        raise CPCError(f"UNSAFE_PATH: {rel!r}")
    if "\\" in rel:
        raise CPCError(f"NONPORTABLE_NAME: {rel}")
    parts = rel.split("/")
    if any(p in ("", ".", "..") for p in parts):
        raise CPCError(f"UNSAFE_PATH: {rel}")
    if len(rel) > MAX_PATH or len(parts) > MAX_DEPTH:
        raise CPCError(f"PATH_LIMIT: {rel}")
    for p in parts:
        stem = p.rstrip(" .").split(".")[0].upper()
        if p.endswith(" ") or p.endswith(".") or stem in WINDOWS_RESERVED:
            raise CPCError(f"NONPORTABLE_NAME: {rel}")
        if any(c in p for c in '<>:"|?*'):
            raise CPCError(f"NONPORTABLE_NAME: {rel}")


def load_cpcignore(source):
    path = os.path.join(source, ".cpcignore")
    patterns = []
    if not os.path.isfile(path):
        return patterns
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            patterns.append(line)
    return patterns

def walk_input(source, archive_mode=False, includes=None, excludes=None):
    source = os.path.abspath(source)
    if not os.path.lexists(source):
        raise CPCError(f"NOT_FOUND: {source}")
    if os.path.islink(source):
        raise CPCError("SYMLINK_UNSUPPORTED")

    root_name = os.path.basename(source.rstrip(os.sep)) or os.path.basename(source)
    portable_name_check(root_name)

    entries = []
    if os.path.isfile(source):
        st = os.stat(source, follow_symlinks=False)
        entries.append(("f", root_name, source, bool(st.st_mode & 0o111), st.st_size))
        return root_name, "file", entries, []

    if not os.path.isdir(source):
        raise CPCError("UNSUPPORTED_INPUT_TYPE")

    # .cpcignore is a chat-profile selection policy. Archive mode ignores it.
    ignore_patterns = [] if archive_mode else load_cpcignore(source)

    excluded = []
    lower_seen = {}
    # root directory is represented explicitly.
    entries.append(("d", root_name, source, True, 0))

    for cur, dirs, files in os.walk(source, topdown=True, followlinks=False):
        # Reject symlink dirs before pruning.
        for d in list(dirs):
            full = os.path.join(cur, d)
            if os.path.islink(full):
                raise CPCError(f"SYMLINK_UNSUPPORTED: {full}")

        rel_cur = os.path.relpath(cur, source)
        rel_cur = "" if rel_cur == "." else posix_rel(rel_cur)

        kept_dirs = []
        for d in sorted(dirs):
            rel_inside = f"{rel_cur}/{d}".strip("/")
            archive_rel = f"{root_name}/{rel_inside}"
            if is_excluded(rel_inside, True, archive_mode, includes, excludes, ignore_patterns):
                excluded.append((archive_rel, "builtin"))
                continue
            portable_name_check(archive_rel)
            key = archive_rel.casefold()
            if key in lower_seen and lower_seen[key] != archive_rel:
                raise CPCError(f"CASE_COLLISION: {lower_seen[key]} <> {archive_rel}")
            lower_seen[key] = archive_rel
            full = os.path.join(cur, d)
            entries.append(("d", archive_rel, full, True, 0))
            kept_dirs.append(d)
        dirs[:] = kept_dirs

        for f in sorted(files):
            full = os.path.join(cur, f)
            if os.path.islink(full):
                raise CPCError(f"SYMLINK_UNSUPPORTED: {full}")
            rel_inside = f"{rel_cur}/{f}".strip("/")
            archive_rel = f"{root_name}/{rel_inside}"
            if is_excluded(rel_inside, False, archive_mode, includes, excludes, ignore_patterns):
                excluded.append((archive_rel, "builtin"))
                continue
            portable_name_check(archive_rel)
            key = archive_rel.casefold()
            if key in lower_seen and lower_seen[key] != archive_rel:
                raise CPCError(f"CASE_COLLISION: {lower_seen[key]} <> {archive_rel}")
            lower_seen[key] = archive_rel
            st = os.stat(full, follow_symlinks=False)
            if not os.path.isfile(full):
                raise CPCError(f"UNSUPPORTED_MEMBER_TYPE: {full}")
            if st.st_size > MAX_FILE:
                raise CPCError(f"FILE_LIMIT: {archive_rel}")
            entries.append(("f", archive_rel, full, bool(st.st_mode & 0o111), st.st_size))

    entries.sort(key=lambda x: x[1].encode("utf-8"))
    return root_name, "dir", entries, excluded

def content_hash(entries):
    h = hashlib.sha256()
    for typ, rel, full, executable, size in entries:
        rel_b = rel.encode("utf-8")
        h.update(typ.encode("ascii") + b"\0")
        h.update(str(len(rel_b)).encode("ascii") + b":" + rel_b + b"\0")
        h.update((b"1" if executable else b"0") + b"\0")
        h.update(str(size).encode("ascii") + b"\0")
        if typ == "f":
            with open(full, "rb") as fh:
                while True:
                    chunk = fh.read(1024 * 1024)
                    if not chunk:
                        break
                    h.update(chunk)
        h.update(b"\0")
    return h.hexdigest()

def make_manifest(entries):
    lines = []
    for typ, rel, full, executable, size in entries:
        digest = "-"
        if typ == "f":
            hh = hashlib.sha256()
            with open(full, "rb") as fh:
                for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                    hh.update(chunk)
            digest = hh.hexdigest()
        lines.append(f"{typ}\t{size}\t{1 if executable else 0}\t{digest}\t{rel}")
    return ("\n".join(lines) + "\n").encode("utf-8")

def make_state(root_name, input_type, archive_mode, source_capsule=""):
    vals = [
        ("v", VERSION),
        ("root", root_name),
        ("type", input_type),
        ("profile", "archive" if archive_mode else "chat"),
        ("codec", CODEC),
    ]
    if source_capsule:
        vals.append(("source", source_capsule))
    return "".join(f"{k}={v}\n" for k, v in vals).encode("utf-8")

def tarinfo(name, typ, size=0, executable=False):
    ti = tarfile.TarInfo(name)
    ti.mtime = 0
    ti.uid = 0
    ti.gid = 0
    ti.uname = ""
    ti.gname = ""
    ti.mode = 0o755 if (typ == "d" or executable) else 0o644
    ti.type = tarfile.DIRTYPE if typ == "d" else tarfile.REGTYPE
    ti.size = 0 if typ == "d" else size
    return ti

def build_tar(source, archive_mode=False, includes=None, excludes=None):
    root_name, input_type, entries, excluded = walk_input(source, archive_mode, includes, excludes)
    c_id = content_hash(entries)
    manifest = make_manifest(entries)
    state = make_state(root_name, input_type, archive_mode)

    bio = io.BytesIO()
    with tarfile.open(fileobj=bio, mode="w", format=tarfile.PAX_FORMAT) as tf:
        # Internal metadata first, fixed names.
        meta_dir = tarinfo(META_ROOT, "d")
        tf.addfile(meta_dir)

        st = tarinfo(f"{META_ROOT}/{STATE_NAME}", "f", len(state), False)
        tf.addfile(st, io.BytesIO(state))

        mi = tarinfo(f"{META_ROOT}/{MANIFEST_NAME}", "f", len(manifest), False)
        tf.addfile(mi, io.BytesIO(manifest))

        for typ, rel, full, executable, size in entries:
            ti = tarinfo(rel, typ, size, executable)
            if typ == "d":
                tf.addfile(ti)
            else:
                # Detect simple source mutation around read.
                before = os.stat(full, follow_symlinks=False)
                with open(full, "rb") as fh:
                    tf.addfile(ti, fh)
                after = os.stat(full, follow_symlinks=False)
                if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise CPCError(f"SOURCE_CHANGED: {full}")

    raw = bio.getvalue()
    if len(raw) > MAX_TAR:
        raise CPCError("TAR_LIMIT")
    return raw, c_id, root_name, input_type, entries, excluded

def encode_capsule(raw, content_id, preset=9):
    # Fixed POC compressor profile. XZ FORMAT_XZ + preset.
    packed = lzma.compress(raw, format=lzma.FORMAT_XZ, preset=preset)
    if len(packed) > MAX_COMPRESSED:
        raise CPCError("COMPRESSED_LIMIT")
    cap_hash = sha256(packed)
    package_id = sha256(raw)
    b64 = base64.b64encode(packed).decode("ascii")
    text = (
        f"#CPC|1|b64>xz>tar|{cap_hash}\n"
        f"{START}\n"
        f"{b64}\n"
        f"{END}\n"
    )
    return text, cap_hash, package_id, packed

def atomic_write(path, data, force=False, backup=False):
    path = os.path.abspath(path)
    parent = os.path.dirname(path) or "."
    os.makedirs(parent, exist_ok=True)
    if os.path.exists(path):
        if not force and not backup:
            raise CPCError(f"DEST_EXISTS: {path}")
        if backup:
            bak = path + ".bak"
            n = 1
            while os.path.exists(bak):
                bak = path + f".bak{n}"
                n += 1
            os.replace(path, bak)
    fd, tmp = tempfile.mkstemp(prefix=".cpc-", suffix=".tmp", dir=parent)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            try:
                os.fsync(fh.fileno())
            except OSError:
                pass
        if os.path.exists(path) and force:
            os.replace(tmp, path)
        else:
            os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

def default_output_for_pack(source):
    source = os.path.abspath(source)
    clean = source.rstrip(os.sep)
    return clean + ".cpc.md"

def parse_capsule(path):
    if os.path.getsize(path) > MAX_CARRIER:
        raise CPCError("CARRIER_LIMIT")
    with open(path, "rb") as fh:
        data = fh.read()
    try:
        md = data.decode("utf-8")
    except UnicodeDecodeError:
        raise CPCError("NOT_CPC")

    lines = md.splitlines()
    if len(lines) < 4 or not lines[0].startswith("#CPC|"):
        raise CPCError("NOT_CPC")
    meta = lines[0].strip().split("|")
    if len(meta) != 4 or meta[0] != "#CPC" or meta[1] != VERSION or meta[2] != "b64>xz>tar":
        raise CPCError("INVALID_METADATA")
    cap_hash = meta[3]
    if len(cap_hash) != 64:
        raise CPCError("INVALID_HASH")

    if md.count(START) != 1 or md.count(END) != 1:
        raise CPCError("INVALID_MARKERS")
    a = md.index(START) + len(START)
    b = md.index(END, a)
    payload_text = "".join(md[a:b].split())
    try:
        packed = base64.b64decode(payload_text, validate=True)
    except Exception:
        raise CPCError("BAD_BASE64")
    if len(packed) > MAX_COMPRESSED:
        raise CPCError("COMPRESSED_LIMIT")
    if sha256(packed) != cap_hash:
        raise CPCError("HASH_MISMATCH")

    try:
        raw = lzma.decompress(packed, format=lzma.FORMAT_AUTO)
    except Exception as e:
        raise CPCError(f"DECOMPRESSION_FAILED: {e}")
    if len(raw) > MAX_TAR:
        raise CPCError("TAR_LIMIT")
    return {
        "version": VERSION,
        "codec": CODEC,
        "capsule_hash": cap_hash,
        "package_id": sha256(raw),
        "content_id": None,
        "raw": raw,
        "packed_size": len(packed),
        "carrier_size": len(data),
    }

def safe_member_name(name):
    portable_name_check(name)
    if name == META_ROOT or name.startswith(META_ROOT + "/"):
        return
    # user members already passed generic checks

def parse_state_bytes(data):
    out = {}
    for line in data.decode("utf-8").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out[k] = v
    return out

def validate_archive(raw):
    members = []
    total = 0
    names = set()
    state = None
    manifest = None

    try:
        tf = tarfile.open(fileobj=io.BytesIO(raw), mode="r:")
    except Exception as e:
        raise CPCError(f"BAD_TAR: {e}")

    with tf:
        all_members = tf.getmembers()
        if len(all_members) > MAX_MEMBERS:
            raise CPCError("MEMBER_LIMIT")
        for m in all_members:
            name = m.name.rstrip("/") if m.isdir() else m.name
            safe_member_name(name)
            if name in names:
                raise CPCError(f"DUPLICATE_MEMBER: {name}")
            names.add(name)

            if not (m.isfile() or m.isdir()):
                raise CPCError(f"UNSUPPORTED_MEMBER_TYPE: {name}")
            if m.isfile():
                if m.size < 0 or m.size > MAX_FILE:
                    raise CPCError(f"FILE_LIMIT: {name}")
                total += m.size
                if total > MAX_TOTAL:
                    raise CPCError("TOTAL_LIMIT")
            members.append(m)

        def read_internal(name):
            try:
                m = tf.getmember(name)
            except KeyError:
                raise CPCError(f"MISSING_INTERNAL: {name}")
            if not m.isfile():
                raise CPCError(f"BAD_INTERNAL: {name}")
            f = tf.extractfile(m)
            if f is None:
                raise CPCError(f"BAD_INTERNAL: {name}")
            return f.read()

        state = parse_state_bytes(read_internal(f"{META_ROOT}/{STATE_NAME}"))
        manifest = read_internal(f"{META_ROOT}/{MANIFEST_NAME}").decode("utf-8")

    # Validate manifest records against archive user members.
    expected = {}
    for line in manifest.splitlines():
        if not line:
            continue
        parts = line.split("\t", 4)
        if len(parts) != 5:
            raise CPCError("BAD_MANIFEST")
        typ, size_s, exec_s, digest, path = parts
        if path in expected:
            raise CPCError(f"DUPLICATE_MANIFEST: {path}")
        expected[path] = (typ, int(size_s), exec_s == "1", digest)

    actual_user = {
        m.name.rstrip("/") if m.isdir() else m.name: m
        for m in members
        if not (m.name == META_ROOT or m.name.startswith(META_ROOT + "/"))
    }
    if set(expected) != set(actual_user):
        raise CPCError("MANIFEST_MEMBER_MISMATCH")

    # Hash regular members and validate type/size/mode.
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as tf:
        for path, rec in expected.items():
            typ, size, executable, digest = rec
            m = tf.getmember(path)
            if typ == "d":
                if not m.isdir() or size != 0 or digest != "-":
                    raise CPCError(f"MANIFEST_MISMATCH: {path}")
            elif typ == "f":
                if not m.isfile() or m.size != size:
                    raise CPCError(f"MANIFEST_MISMATCH: {path}")
                f = tf.extractfile(m)
                hh = hashlib.sha256()
                for chunk in iter(lambda: f.read(1024 * 1024), b""):
                    hh.update(chunk)
                if hh.hexdigest() != digest:
                    raise CPCError(f"FILE_HASH_MISMATCH: {path}")
            else:
                raise CPCError(f"BAD_MANIFEST_TYPE: {path}")
    return members, state, expected

def recompute_content_id(raw, expected):
    h = hashlib.sha256()
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as tf:
        for path in sorted(expected, key=lambda p: p.encode("utf-8")):
            typ, size, executable, digest = expected[path]
            rel_b = path.encode("utf-8")
            h.update(typ.encode("ascii") + b"\0")
            h.update(str(len(rel_b)).encode("ascii") + b":" + rel_b + b"\0")
            h.update((b"1" if executable else b"0") + b"\0")
            h.update(str(size).encode("ascii") + b"\0")
            if typ == "f":
                f = tf.extractfile(tf.getmember(path))
                for chunk in iter(lambda: f.read(1024 * 1024), b""):
                    h.update(chunk)
            h.update(b"\0")
    return h.hexdigest()

def full_verify(path):
    info = parse_capsule(path)
    members, state, expected = validate_archive(info["raw"])
    actual_content = recompute_content_id(info["raw"], expected)
    info["content_id"] = actual_content
    info.update({
        "members": members,
        "state": state,
        "manifest": expected,
        "user_members": len(expected),
        "raw_size": len(info["raw"]),
    })
    return info

def is_capsule(path):
    if not os.path.isfile(path):
        return False
    try:
        with open(path, "rb") as fh:
            head = fh.read(6)
        return head == b"#CPC|"
    except OSError:
        return False

def source_stats(source):
    if os.path.isfile(source):
        return os.path.getsize(source)
    total = 0
    for cur, dirs, files in os.walk(source):
        for f in files:
            p = os.path.join(cur, f)
            if os.path.isfile(p) and not os.path.islink(p):
                try:
                    total += os.path.getsize(p)
                except OSError:
                    pass
    return total

def pack(source, output=None, force=False, backup=False, archive_mode=False, preset=9, includes=None, excludes=None):
    source = os.path.abspath(source)
    out = output or default_output_for_pack(source)
    raw, content_id, root_name, input_type, entries, excluded = build_tar(source, archive_mode, includes, excludes)
    text, cap_hash, package_id, packed = encode_capsule(raw, content_id, preset=preset)
    atomic_write(out, text.encode("utf-8"), force=force, backup=backup)
    # verify what was actually published
    info = full_verify(out)
    return {
        "output": os.path.abspath(out),
        "root": root_name,
        "type": input_type,
        "content_id": content_id,
        "package_id": package_id,
        "capsule_hash": cap_hash,
        "files": sum(1 for e in entries if e[0] == "f"),
        "dirs": sum(1 for e in entries if e[0] == "d"),
        "excluded": excluded,
        "source_bytes": source_stats(source),
        "carrier_bytes": os.path.getsize(out),
        "verified": True,
    }

def safe_join(root, archive_name):
    parts = archive_name.split("/")
    dest = os.path.abspath(os.path.join(root, *parts))
    base = os.path.abspath(root)
    if os.path.commonpath([base, dest]) != base:
        raise CPCError(f"UNSAFE_PATH: {archive_name}")
    return dest

def write_state_sidecar(dest_root, capsule_path, info):
    state = info["state"]
    logical = state.get("root", os.path.basename(dest_root))
    sidecar = os.path.join(os.path.dirname(dest_root), f".{os.path.basename(dest_root)}.cpc-state")
    text = (
        f"v={VERSION}\n"
        f"root={logical}\n"
        f"profile={state.get('profile','chat')}\n"
        f"source={os.path.abspath(capsule_path)}\n"
        f"content_id={info['content_id']}\n"
    )
    atomic_write(sidecar, text.encode("utf-8"), force=True)
    return sidecar

def unpack(capsule, output=None, force=False, backup=False, selected=None):
    capsule = os.path.abspath(capsule)
    info = full_verify(capsule)
    state = info["state"]
    root_name = state.get("root")
    if not root_name:
        raise CPCError("MISSING_ROOT_STATE")

    if selected is None:
        if output:
            dest_parent = os.path.abspath(output)
            # explicit output is the containing destination for logical root
            final_root = os.path.join(dest_parent, root_name)
        else:
            final_root = os.path.join(os.path.dirname(capsule), root_name)
    else:
        # selected extraction output is destination directory itself.
        final_root = os.path.abspath(output or (os.path.splitext(os.path.basename(capsule))[0] + ".extract"))

    if os.path.exists(final_root):
        if not force and not backup:
            raise CPCError(f"DEST_EXISTS: {final_root}")
        if backup:
            bak = final_root + ".bak"
            n = 1
            while os.path.exists(bak):
                bak = final_root + f".bak{n}"
                n += 1
            os.replace(final_root, bak)
        elif force:
            if os.path.isdir(final_root):
                shutil.rmtree(final_root)
            else:
                os.unlink(final_root)

    parent = os.path.dirname(final_root) or "."
    os.makedirs(parent, exist_ok=True)
    stage = tempfile.mkdtemp(prefix=".cpc-stage-", dir=parent)
    try:
        with tarfile.open(fileobj=io.BytesIO(info["raw"]), mode="r:") as tf:
            for m in info["members"]:
                name = m.name.rstrip("/") if m.isdir() else m.name
                if name == META_ROOT or name.startswith(META_ROOT + "/"):
                    continue

                if selected is not None:
                    sel = selected.strip("/")
                    if name != sel and not name.startswith(sel + "/"):
                        continue
                    # strip common selected prefix for convenient selective extraction
                    relname = name
                else:
                    relname = name

                dest = safe_join(stage, relname)
                if m.isdir():
                    os.makedirs(dest, exist_ok=True)
                    try:
                        os.chmod(dest, 0o755)
                    except OSError:
                        pass
                elif m.isfile():
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    src = tf.extractfile(m)
                    with open(dest, "wb") as out:
                        shutil.copyfileobj(src, out, length=1024 * 1024)
                    try:
                        os.chmod(dest, 0o755 if (m.mode & 0o111) else 0o644)
                    except OSError:
                        pass

        # For full extraction, stage contains logical root; publish that root.
        if selected is None:
            staged_root = os.path.join(stage, root_name)
            if not os.path.exists(staged_root):
                raise CPCError("MISSING_LOGICAL_ROOT")
            os.replace(staged_root, final_root)
            sidecar = write_state_sidecar(final_root, capsule, info)
        else:
            # publish stage contents as requested output directory
            os.replace(stage, final_root)
            stage = None
            sidecar = None
    finally:
        if stage and os.path.exists(stage):
            shutil.rmtree(stage, ignore_errors=True)

    return final_root, sidecar, info

def read_sidecar_for(path):
    p = os.path.abspath(path)
    base = os.path.basename(p.rstrip(os.sep))
    side = os.path.join(os.path.dirname(p.rstrip(os.sep)), f".{base}.cpc-state")
    if not os.path.isfile(side):
        raise CPCError(f"STATE_NOT_FOUND: {side}")
    vals = {}
    with open(side, "r", encoding="utf-8") as fh:
        for line in fh:
            if "=" in line:
                k, v = line.rstrip("\n").split("=", 1)
                vals[k] = v
    return side, vals

def repack(path, output=None, force=False, backup=False, preset=9):
    _, state = read_sidecar_for(path)
    archive_mode = state.get("profile") == "archive"
    out = output or state.get("source") or default_output_for_pack(path)
    # Repack a recovered logical root as exactly that root.
    return pack(path, output=out, force=force, backup=backup,
                archive_mode=archive_mode, preset=preset)

def list_capsule(path):
    info = full_verify(path)
    for p in sorted(info["manifest"]):
        print(p)
    return info

def inspect_capsule(path):
    info = full_verify(path)
    st = info["state"]
    return {
        "version": info["version"],
        "codec": info["codec"],
        "root": st.get("root", "?"),
        "profile": st.get("profile", "?"),
        "members": info["user_members"],
        "carrier_bytes": info["carrier_size"],
        "compressed_bytes": info["packed_size"],
        "tar_bytes": info["raw_size"],
        "capsule_hash": info["capsule_hash"],
        "package_id": info["package_id"],
        "content_id": info["content_id"],
    }

def filesystem_manifest(path, archive_mode=False):
    _, _, entries, _ = walk_input(path, archive_mode)
    out = {}
    for typ, rel, full, executable, size in entries:
        digest = "-"
        if typ == "f":
            hh = hashlib.sha256()
            with open(full, "rb") as fh:
                for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                    hh.update(chunk)
            digest = hh.hexdigest()
        out[rel] = (typ, size, executable, digest)
    return out

def compare(capsule, path):
    info = full_verify(capsule)
    archive_mode = info["state"].get("profile") == "archive"
    current = filesystem_manifest(path, archive_mode)
    expected = info["manifest"]

    added = sorted(set(current) - set(expected))
    removed = sorted(set(expected) - set(current))
    changed = []
    unchanged = []
    for p in sorted(set(current) & set(expected)):
        if current[p] == expected[p]:
            unchanged.append(p)
        else:
            changed.append(p)
    return added, removed, changed, unchanged

def human_bytes(n):
    x = float(n)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if x < 1024 or unit == "TiB":
            return f"{x:.1f}{unit}" if unit != "B" else f"{int(x)}B"
        x /= 1024

def parser():
    p = argparse.ArgumentParser(prog="cpc", add_help=True)
    p.add_argument("--version", action="version", version=f"CPC {RELEASE_VERSION} (wire {VERSION})")
    p.add_argument("args", nargs="*")
    p.add_argument("-o", "--output")
    p.add_argument("-f", "--force", action="store_true")
    p.add_argument("-b", "--backup", action="store_true")
    p.add_argument("-q", "--quiet", action="store_true")
    p.add_argument("-V", "--verbose", action="store_true")
    p.add_argument("-a", "--archive", action="store_true")
    p.add_argument("-m", "--max", action="store_true")
    p.add_argument("--include", action="append", default=[], metavar="GLOB",
                   help="force-include paths matching GLOB, overriding automatic ignores")
    p.add_argument("--exclude", action="append", default=[], metavar="GLOB",
                   help="exclude paths matching GLOB; may be repeated")
    return p

def main(argv=None):
    ns = parser().parse_args(argv)
    args = ns.args
    preset = 9 | lzma.PRESET_EXTREME if ns.max else 9

    try:
        if not args:
            result = pack(".", ns.output, ns.force, ns.backup, ns.archive, preset, ns.include, ns.exclude)
            if not ns.quiet:
                print(f"CPC PASS {human_bytes(result['source_bytes'])} -> {human_bytes(result['carrier_bytes'])}")
                print(f"-> {result['output']}")
            return 0

        verbs = {"p","u","r","v","l","i","c","x","n",
                 "pack","unpack","repack","verify","list","inspect","compare","extract","rename-root"}
        verb = args[0] if args[0] in verbs else None

        if verb is None:
            target = args[0]
            if is_capsule(target):
                out, side, info = unpack(target, ns.output, ns.force, ns.backup)
                if not ns.quiet:
                    print(f"CPC PASS files={info['user_members']}")
                    print(f"-> {out}")
                return 0
            result = pack(target, ns.output, ns.force, ns.backup, ns.archive, preset, ns.include, ns.exclude)
            if not ns.quiet:
                print(f"CPC PASS {human_bytes(result['source_bytes'])} -> {human_bytes(result['carrier_bytes'])}")
                print(f"-> {result['output']}")
            return 0

        if verb in ("p","pack"):
            target = args[1] if len(args) > 1 else "."
            result = pack(target, ns.output, ns.force, ns.backup, ns.archive, preset, ns.include, ns.exclude)
            if not ns.quiet:
                print(f"CPC PASS {human_bytes(result['source_bytes'])} -> {human_bytes(result['carrier_bytes'])}")
                print(f"-> {result['output']}")
            return 0

        if verb in ("u","unpack"):
            if len(args) != 2:
                raise CPCError("USAGE: cpc u <capsule>")
            out, side, info = unpack(args[1], ns.output, ns.force, ns.backup)
            if not ns.quiet:
                print(f"CPC PASS files={info['user_members']}")
                print(f"-> {out}")
            return 0

        if verb in ("r","repack"):
            if len(args) != 2:
                raise CPCError("USAGE: cpc r <path>")
            result = repack(args[1], ns.output, ns.force, ns.backup, preset)
            if not ns.quiet:
                print(f"CPC PASS files={result['files']}")
                print(f"-> {result['output']}")
            return 0

        if verb in ("v","verify"):
            if len(args) != 2:
                raise CPCError("USAGE: cpc v <capsule>")
            info = full_verify(args[1])
            if not ns.quiet:
                print(f"CPC PASS v={info['version']} files={info['user_members']} packed={human_bytes(info['carrier_size'])}")
                print(f"content={info['content_id']}")
            return 0

        if verb in ("l","list"):
            if len(args) != 2:
                raise CPCError("USAGE: cpc l <capsule>")
            list_capsule(args[1])
            return 0

        if verb in ("i","inspect"):
            if len(args) != 2:
                raise CPCError("USAGE: cpc i <capsule>")
            d = inspect_capsule(args[1])
            for k, v in d.items():
                print(f"{k}: {v}")
            return 0

        if verb in ("c","compare"):
            if len(args) != 3:
                raise CPCError("USAGE: cpc c <capsule> <path>")
            added, removed, changed, unchanged = compare(args[1], args[2])
            for label, values in (("ADDED", added),("REMOVED",removed),("CHANGED",changed)):
                for v in values:
                    print(f"{label}\t{v}")
            if not (added or removed or changed):
                print(f"CPC EQUAL unchanged={len(unchanged)}")
                return 0
            return 1

        if verb in ("x","extract"):
            if len(args) != 3:
                raise CPCError("USAGE: cpc x <capsule> <member>")
            out, _, _ = unpack(args[1], ns.output, ns.force, ns.backup, selected=args[2])
            print(f"CPC PASS -> {out}")
            return 0

        if verb in ("n","rename-root"):
            if len(args) != 3:
                raise CPCError("USAGE: cpc n <capsule> <new-root>")
            # Deliberately implemented as safe unpack-to-temp + rename + fresh pack.
            cap = os.path.abspath(args[1])
            newroot = args[2]
            portable_name_check(newroot)
            temp = tempfile.mkdtemp(prefix="cpc-rename-")
            try:
                oldroot, _, info = unpack(cap, output=temp)
                renamed = os.path.join(temp, newroot)
                os.replace(oldroot, renamed)
                out = ns.output or cap
                result = pack(
                    renamed, out, force=True if out == cap else ns.force,
                    backup=ns.backup,
                    archive_mode=info["state"].get("profile") == "archive",
                    preset=preset,
                )
                print(f"CPC PASS -> {result['output']}")
                return 0
            finally:
                shutil.rmtree(temp, ignore_errors=True)

        raise CPCError("UNKNOWN_COMMAND")

    except CPCError as e:
        print(f"CPC FAIL {e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("CPC FAIL INTERRUPTED", file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
