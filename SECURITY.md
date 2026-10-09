# Security Policy

## Supported version

CPC is currently pre-1.0. Security fixes target the latest release candidate.

| Release | Supported |
|---|---|
| 0.3.x RC | Yes |
| Earlier POCs | No |

## Reporting a vulnerability

Do not publish an exploit or malicious capsule as a public issue before maintainers have had a chance to review it.

For now, use GitHub private vulnerability reporting if enabled for the repository. If private reporting is unavailable, open a minimal issue requesting a private contact channel without posting exploit details.

## Security model

The normative threat model is maintained in [`standard/SECURITY.md`](standard/SECURITY.md).

CPC treats capsules as untrusted input. Implementations are expected to validate paths, member types, resource limits, and integrity before publishing extracted files.

## Reference implementation limits

The following ceilings apply to the 0.3.0-rc.6 reference reader in `bin/cpc.py`. They are receiver policy, not intrinsic wire-format limits. Other receivers should publish their limits and may choose lower ceilings for constrained sandboxes.

| Resource | Ceiling |
|---|---:|
| Markdown carrier file | 512 MiB (536,870,912 bytes) |
| Decoded compressed payload | 384 MiB (402,653,184 bytes) |
| Expanded TAR stream, including metadata/padding | 2 GiB (2,147,483,648 bytes) |
| LZMA decoder memory | 128 MiB (134,217,728 bytes) |
| Physical TAR headers, including hidden PAX/GNU extensions and internal metadata | 200,000 |
| Individual regular file | 1 GiB (1,073,741,824 bytes) |
| Sum of declared regular-file sizes, including internal metadata | 2 GiB (2,147,483,648 bytes) |
| Member path length | 1,024 Python Unicode characters |
| Member path depth | 100 slash-separated components |
| Each PAX/GNU extension payload | 1 MiB (1,048,576 bytes, excluding block padding) |
| Cumulative extension payloads plus CPC internal-file contents | 16 MiB (16,777,216 bytes, excluding headers and padding) |
| Consecutive nested extension headers | 32 |
| Preserved modification times | UTC years 0001-9999; at most 9 fractional digits; no exponent/nonfinite values |
| Multipart set | 1,000 parts; reconstructed carrier remains limited to 512 MiB |
| Expansion ratio | No ratio limit is implemented |

SHA-256 is checked on the compressed bytes before decompression. A matching hash establishes integrity, not trust: an attacker can hash their own hostile payload.

The reader parses the carrier in chunks, including capsules whose Base64 is on one long line. Decoded XZ bytes are counted and hashed while written to a temporary file. Only after the hash matches does decompression begin. Expanded TAR bytes are written to another temporary file with a running size check; decoding requests at most one byte beyond the remaining ceiling to detect excess. Normal I/O chunks are at most 1 MiB. The LZMA decoder has a separate memory limit.

Physical headers are counted before TAR member processing, including PAX/GNU extensions that `tarfile` hides from normal iteration. Extension sizes and their cumulative budget are checked before reading their bodies. Resolved CPC internal-file sizes consume the same budget during iteration, before any internal file is loaded. Ordinary 512-byte headers are counted separately, not charged to the 16 MiB payload budget. A depth ceiling bounds recursive extension processing. The reference implementation uses the CPython `TarInfo._proc_member` hook; the security regressions run across supported Python versions in CI.

The reader accepts one complete XZ stream and rejects incomplete streams, additional streams, and trailing compressed-payload data. ASCII whitespace is accepted within Base64, including across chunk boundaries; extra envelope content and duplicate markers are rejected.

**These ceilings are not a hard process-memory budget.** Large payload intermediates live on disk, but the compressor/decoder and the index of paths, TAR members, and manifest records still use RAM. Metadata memory grows with file count and path lengths. Preset 6 is the default; explicit preset 9 packing can consume substantial compressor memory even with chunked I/O. Use an isolated process with external memory and disk quotas for untrusted capsules, and lower receiver ceilings for constrained sandboxes.

Temporary space must accommodate the compressed payload and expanded TAR, and later the TAR plus staged output. Packing self-verification may also retain its compressed intermediate alongside these files. Files are validated before publication. Existing output is preserved when capsule verification or extraction staging fails; replacement occurs only after the new capsule verifies or extraction staging succeeds. Temporary files and incomplete staging directories are cleaned up through context managers and `finally` blocks on handled failures. A completed extraction is deliberately retained when publication fails, and its path is printed. If replacement rollback also fails, the previous tree is retained at the reported backup/scratch path instead of being deleted by cleanup. Windows access/sharing errors receive bounded retries (3.15 seconds of waiting per rename); persistent failures remain errors. There is no automatic partial-copy fallback or permission/AV bypass. Abrupt process termination can still leave staging directories. This is disk-backed processing with multiple validation passes, not a one-pass network stream.

High compression ratio alone is not classified as an attack: repetitive text can compress extremely well. The current implementation uses absolute size checks rather than a ratio threshold. It does not guarantee safe processing up to the published maxima on every machine.

Preserved timestamps are untrusted metadata. Their original TAR/PAX representation is validated before extraction and parsed with integer arithmetic to avoid floating-point precision loss. Dates are applied only within staging, before publication; denied or unsupported timestamp writes report `TIMESTAMP_RESTORE_FAILED` and preserve an existing destination. The user can explicitly request `--normalize-times` to discard original dates. Filesystem precision may still round valid dates. PAX timestamp records count toward the existing header, metadata, TAR and carrier ceilings; preservation does not relax any resource limit.

Multipart joining uses bounded header reads and at most 1 MiB body reads, rejects claimed reconstructed sizes above the carrier ceiling before body processing, and aborts if received bytes exceed the declared total. It validates every part, the whole reconstructed carrier and the CPC archive before publication. Hashes are not authentication. Export and join stage outputs in temporary directories and require a new destination; they do not promise protection against hostile concurrent filesystem changes or power-loss durability. Splitting does not relax aggregate receiver limits. Export self-checking temporarily needs space for the original capsule, part files, a reconstructed capsule and normal verification intermediates.

Multipart `HANDOFF.md` includes a readable copy of the standalone receiver so an offline fresh sandbox can restore with Python alone. This is executable code supplied with the export, not a trusted bootloader: review it before use. No project file is executed during join or restoration. A subprocess regression runs only the exported receiver and attachments with Python isolated mode, checking successful recovery and missing/corrupt-part failures without repository imports or an installed CPC tool.

Basic `u`/`v`, explicit `recover` and full `--strict` auditing share carrier, hash, decoder and TAR safety checks. Basic unpack and recovery share extraction code. In basic mode and recovery, only CPC semantic metadata failures become diagnostics: missing/invalid state, malformed/stale manifests, root-layout mismatches and stale inner file hashes. A matching outer hash is mandatory and does not authenticate either the payload or its claimed metadata. Recovery records the first metadata failure, not an exhaustive audit, and does not establish original completeness. Original `.cpc` entries are retained as evidence outside the recovered tree; fresh workflow state is derived from TAR facts rather than untrusted state declarations. Recovery never executes project code or imports recovered Python. All content, evidence, report and new state are staged before publication to a new destination.

All reader modes check implied parent paths for case and file/directory conflicts. The member ceiling also bounds explicit and implied filesystem paths. Complete TAR end blocks are required; nonzero data following the final member, concatenated TAR archives and truncated file bodies are rejected before extraction. Recovery retains the other existing resource ceilings. As with ordinary extraction, hostile concurrent changes to the destination parent and abrupt process termination are outside the atomic-publication guarantee.

Normal unpack creates no adjacent state unless `--state` is requested. Unverified metadata never supplies output paths or policy. A single actual top-level item determines the root; multiple roots require an explicit output directory. Whole-tree replacement requires `-f` or `-b` and occurs after staged extraction. Existing adjacent state blocks a stateless restore to avoid silently reusing stale settings. Optional sidecar writes retain the legacy post-publication behavior: a sidecar-write failure can leave a successfully restored tree; default stateless restore does not have that additional write.
