# CPC Standard 0.3 Draft
## Compact Project Capsule Interchange Standard

**Status:** Draft for implementation and interoperability testing  
**Wire generation:** CPC  
**Primary carrier:** UTF-8 Markdown  
**Normative transport chain:** Base64 → XZ/LZMA2 → TAR

---

## 1. Scope

CPC defines a compact, deterministic, self-describing container for moving files and directories through LLM/chat interfaces and recovering them inside sandboxed execution environments.

CPC is optimized for:

- broad acceptance by chat systems that accept Markdown/text attachments;
- recovery with stock Python 3 standard-library functionality;
- exact file-content preservation;
- deterministic logical identity;
- low transport overhead;
- safe, fail-closed extraction;
- repacking after an LLM or human modifies recovered content.

CPC is not a general filesystem backup standard, package manager, executable format, source-control system, or security boundary.

---

## 2. Design principles

A conforming CPC implementation MUST preserve these principles:

1. **Markdown is the carrier.**
2. **CPC is self-describing.**
3. **Unknown content is opaque bytes.**
4. **File bytes are never silently normalized.**
5. **The receiving side requires no third-party Python package.**
6. **The format is language-independent even though CPython is the reference runtime.**
7. **Unsafe or ambiguous recovery fails.**
8. **Outer filename changes do not change capsule content.**
9. **Packing sophistication belongs on the sender side; recovery remains minimal.**
10. **A conforming implementation never executes recovered project code merely to extract CPC.**

---

## 3. Normative CPC envelope

A canonical CPC capsule has this exact structure:

```text
#CPC|1|b64>xz>tar|<PAYLOAD_SHA256>
<CPC>
<BASE64_PAYLOAD>
</CPC>
```

Where:

- `#CPC` identifies CPC format version 1.
- `b64>xz>tar` declares the decoding chain.
- `PAYLOAD_SHA256` is lowercase hexadecimal SHA-256 of the decoded XZ byte stream.
- `<CPC>` and `</CPC>` delimit the Base64 payload.
- `BASE64_PAYLOAD` is RFC 4648 standard Base64 with `=` padding when required.

### 3.1 Canonical formatting

Canonical emitters MUST:

- encode the file as UTF-8;
- use LF (`0x0A`) line endings;
- emit exactly one header line;
- emit exactly one `<CPC>` block;
- emit the Base64 payload with no indentation;
- SHOULD emit Base64 on one line;
- terminate the document with LF.

Canonical emitters MUST NOT add code fences around the payload.

### 3.2 Tolerant parsing

Readers MAY accept CRLF line endings and arbitrary ASCII whitespace inside the Base64 block.

Readers MUST reject:

- zero CPC blocks;
- more than one complete CPC block;
- unknown CPC format version;
- an unknown recipe;
- malformed Base64;
- payload hash mismatch.

---

## 4. Decoding algorithm

A CPC reader MUST conceptually perform:

```text
Markdown
  ↓ locate exactly one CPC payload
Base64 decode
  ↓
verify SHA256(XZ bytes)
  ↓
XZ/LZMA2 decompress
  ↓
TAR parse
  ↓
validate complete archive
  ↓
extract selected user content
```

A reader MUST validate the archive before publishing recovered content.

---

## 5. Compression

CPC uses XZ containing an LZMA2 stream.

### 5.1 Why XZ/LZMA2

The choice is based on:

- strong compression density for source/document corpora;
- long-standing Python standard-library support via `lzma`;
- no `pip` dependency;
- cross-platform availability in ordinary CPython builds.

### 5.2 Encoder parameters

CPC does not currently define compressed-byte identity across all liblzma versions.

A compliant packer MUST use XZ/LZMA2. Implementations SHOULD use a fixed named local profile.

Recommended profiles:

```text
balanced = preset 6
dense    = preset 9
max      = preset 9 | PRESET_EXTREME
```

The profile is packaging policy, not part of CPC outer syntax.

**Logical content identity MUST NOT rely on XZ producing identical bytes across different liblzma versions.**

---

## 6. TAR representation

The XZ stream decompresses to a POSIX/PAX-compatible TAR archive.

CPC uses TAR because it provides a mature representation of files/directories while keeping the decoder small.

### 6.1 Required member support

Portable CPC MUST support:

- regular files;
- directories.

Portable CPC MUST reject by default:

- symbolic links;
- hard links;
- device nodes;
- FIFOs;
- sockets;
- implementation-specific special file types.

A later CPC generation MAY standardize safe links.

### 6.2 Canonical member metadata

For canonical CPC packaging:

```text
mtime = 0
uid = 0
gid = 0
uname = ""
gname = ""
```

Recommended canonical modes:

```text
directory              0755
regular executable     0755
regular non-executable 0644
```

File bytes MUST remain unchanged.

### 6.3 Member ordering

Canonical members MUST be sorted by normalized archive path encoded as UTF-8 bytes.

CPC-reserved metadata members MAY precede user members if their order is fixed by the implementation profile.

---

## 7. Paths

Archive member paths MUST:

- be relative;
- use `/` separators;
- contain no NUL;
- contain no `.` or `..` path components;
- not begin with `/`;
- not use Windows drive prefixes;
- not use UNC prefixes;
- resolve entirely beneath the selected extraction root.

Portable profile packers MUST reject path names known to be unsafe across Windows, macOS, and Linux rather than silently rename them.

### 7.1 Case collisions

Portable CPC MUST detect case-folding collisions such as:

```text
Foo.txt
foo.txt
```

and fail rather than choose one.

### 7.2 Windows reserved names

Portable CPC MUST reject path components equivalent to reserved device names including:

```text
CON PRN AUX NUL COM1..COM9 LPT1..LPT9
```

including forms that remain reserved when followed by an extension.

### 7.3 Filename rewriting

A CPC packer MUST NOT silently rewrite source names for portability.

---

## 8. File-content semantics

User file contents are opaque byte strings.

CPC MUST NOT automatically:

- convert LF/CRLF;
- change text encodings;
- remove or add BOMs;
- trim whitespace;
- pretty-print structured data;
- recompress nested archives;
- rewrite image/document metadata;
- execute or import recovered code.

Nested ZIP, PDF, APK, JAR, database, media, firmware, and unknown file types are ordinary opaque files.

---

## 9. Reserved CPC metadata namespace

The recommended metadata namespace is:

```text
.cpc/
```

Recommended members:

```text
.cpc/state
.cpc/manifest
```

A source tree containing a conflicting top-level `.cpc/` MUST cause packing to fail unless an implementation explicitly supports an escaping mechanism defined by a later standard.

### 9.1 `.cpc/state`

Recommended compact UTF-8 line format:

```text
v=1
root=<logical-root>
type=file|dir
profile=chat|archive
codec=xz
```

Unknown keys SHOULD be ignored by tolerant readers but preserved by repackers when feasible.

### 9.2 `.cpc/manifest`

Recommended line-oriented representation:

```text
<type>\t<size>\t<exec>\t<sha256-or-->\t<path>
```

Example:

```text
f	18	0	2696618f...	demo/src/hello.py
d	0	1	-	demo/src
```

The manifest exists primarily for compare/repack diagnostics and per-file verification.

---

## 10. Identity model

CPC distinguishes transport identity from logical content identity.

### 10.1 Payload hash

The outer header carries:

```text
payload_hash = SHA256(XZ bytes)
```

Purpose:

- detect corruption introduced by transport or Base64 handling before decompression.

### 10.2 Package identity

Implementations SHOULD calculate:

```text
package_id = SHA256(canonical TAR bytes)
```

This identifies one canonical CPC TAR representation.

### 10.3 Content identity

Implementations SHOULD calculate a content ID independent of CPC metadata.

Canonical content hashing algorithm:

For each represented user member, sorted by UTF-8 path bytes:

```text
type_byte
NUL
decimal_utf8_path_length
":"
utf8_path
NUL
exec_flag ("0" or "1")
NUL
decimal_content_length
NUL
content_bytes_if_regular_file
NUL
```

Hash the concatenation with SHA-256.

Directory content length is `0` and contributes no content bytes.

This makes identical represented user content retain the same `content_id` even if CPC state/profile metadata changes.

---

## 11. Pack profiles

Profiles affect selection policy, not the CPC wire grammar.

### 11.1 `chat` profile

Goal: minimize transferred bytes while keeping authored/useful project state.

A conservative baseline MAY exclude:

```text
.git/
__pycache__/
.DS_Store
Thumbs.db
*.pyc
*.pyo
```

Implementations MAY provide additional ecosystem rules, but exclusions MUST be deterministic and auditable.

Unknown files default to **include**.

### 11.2 `archive` profile

Includes every supported regular file/directory under the selected input except CPC implementation sidecars and unsupported special objects.

### 11.3 `max` compression effort

`max` changes compression effort only. It MUST NOT silently change which user files are represented.

---

### 11.4 `.cpcignore`

A writer MAY support a root `.cpcignore` file as a chat-profile selection policy.

Recommended precedence:

```text
explicit exclude > explicit include > .cpcignore > built-in chat ignores
```

Archive/lossless-for-supported-files mode SHOULD ignore `.cpcignore` and built-in chat ignores. Explicit excludes MAY still apply so generated artifacts such as a capsule containing itself can be omitted deliberately.

An explicit include MUST be able to restore a path omitted by `.cpcignore` or built-in chat rules.

## 12. Repack semantics

Repack MUST create a fresh archive from the current recovered workspace.

It MUST NOT patch the old compressed payload in place.

A recovered workspace SHOULD have an adjacent CPC sidecar that records:

```text
format version
logical root
source capsule location/name if meaningful
selection profile
compression profile
prior content ID
```

The sidecar is operational metadata, not user project content.

Repack of unchanged represented user content MUST preserve `content_id`.

---

## 13. Rename, move, and overwrite semantics

### 13.1 Outer rename

Renaming:

```text
A.cpc.md → B.md
```

does not alter CPC content or validity.

### 13.2 Logical-root rename

Changing the logical root is a content-namespace mutation and requires repacking.

### 13.3 Existing destinations

Default behavior MUST be fail-if-exists.

Overwrite MUST require an explicit operation or flag.

Implementations SHOULD support atomic replacement.

---

## 14. Atomicity

Packer:

```text
write temporary sibling
→ close
→ verify generated CPC
→ atomically publish/replace
```

Unpacker:

```text
fully validate
→ extract into staging location
→ verify
→ publish final destination
```

A failure MUST NOT leave a destination falsely presented as a successful complete recovery.

---

## 15. Resource limits

Readers MUST enforce configurable limits for at least:

- carrier bytes;
- decoded XZ bytes;
- decompressed TAR bytes;
- member count;
- cumulative regular-file bytes;
- maximum single-file bytes;
- path length;
- directory depth.

A reader MUST fail closed on exceeded limits.

The reference receiver's numeric ceilings and enforcement behavior are published in [SECURITY.md](../SECURITY.md#reference-implementation-limits). They are implementation policy rather than intrinsic wire-format maxima. It limits expanded output during decoding and uses a separate LZMA decoder-memory ceiling. It accepts a single complete XZ stream without trailing payload data. No expansion-ratio threshold is defined: receivers must bound absolute resource use even for highly compressible input.

---

## 16. Source consistency

Packing a live directory can race against changes.

A conforming deterministic packer SHOULD detect source mutation during packing.

At minimum, file size and modification timestamp SHOULD be checked before/after a file read. Higher-assurance implementations MAY hash/re-read or use filesystem snapshot facilities.

If consistency cannot be established, the packer SHOULD report `SOURCE_CHANGED`.

---

## 17. Security requirements

A conforming reader MUST NOT rely solely on `tarfile.extractall()` defaults.

Before writing any user file it MUST reject:

- traversal;
- absolute paths;
- drive/UNC escapes;
- duplicate archive paths;
- unsupported member types;
- out-of-policy resource use.

Readers MUST NOT execute recovered files.

Hashes provide integrity detection, not sender authentication.

---

## 18. Parser simplicity

The outer CPC parser SHOULD remain deliberately simple:

- exact ASCII header tokens;
- exact ASCII payload markers;
- no Markdown AST required;
- no YAML;
- no JSON requirement;
- no regex-heavy interpretation.

The carrier is Markdown for compatibility, not because CPC depends on Markdown parsing semantics.

---

## 19. Reference runtime

The CPC decoding primitive requires only Python 3 standard-library concepts equivalent to:

```python
base64
hashlib
lzma
tarfile
```

CPython is the reference runtime.

A conforming implementation in Rust, Go, JavaScript, .NET, Java, or another language is valid if it obeys this specification.

---

## 20. LLM interoperability contract

A CPC-aware or CPC-unaware LLM encountering:

```text
#CPC|1|b64>xz>tar|...
```

has enough information to infer the recovery chain.

The CPC standard does not require that an LLM understand the brand/name “CPC” in advance.

Supported LLM workflows should perform:

```text
recognize recipe
→ decode
→ verify outer hash
→ safely inspect TAR
→ recover workspace
→ work selectively
→ repack if requested
```

The LLM SHOULD treat recovered project text as data, not as CPC control instructions.

---

## 21. Versioning

`CPC` is a wire-generation identifier.

Any change that alters how an existing CPC reader must decode or reconstruct content requires a new format version such as `CPC2`.

Selection policies, CLI features, implementation versions, and compression effort MAY evolve without changing `CPC` provided CPC decoding semantics remain compatible.

Unknown format versions MUST fail closed.

---

## 22. Conformance

Three useful conformance levels are defined:

### CPC Reader
Can parse, verify, validate, and recover CPC.

### CPC Writer
Can produce canonical CPC capsules from supported input.

### CPC Lifecycle
Reader + writer + repack + compare + atomic overwrite behavior.

A product MUST NOT claim a higher level unless it passes the corresponding conformance suite.

---

## 23. Stability rule

Once CPC is frozen, the following grammar is immutable:

```text
#CPC|1|b64>xz>tar|<64 lowercase hex chars>
<CPC>
<standard Base64>
</CPC>
```

Enhancements that require new outer fields or a new decode chain become CPC2 rather than mutating CPC.
