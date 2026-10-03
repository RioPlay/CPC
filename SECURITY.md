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
| TAR members, including internal metadata | 200,000 |
| Individual regular file | 1 GiB (1,073,741,824 bytes) |
| Sum of declared regular-file sizes, including internal metadata | 2 GiB (2,147,483,648 bytes) |
| Member path length | 1,024 Python Unicode characters |
| Member path depth | 100 slash-separated components |
| Each internal state/manifest file and TAR extension read | 16 MiB (16,777,216 bytes; TAR block padding allowed for extension reads) |
| Expansion ratio | No ratio limit is implemented |

SHA-256 is checked on the compressed bytes before decompression. A matching hash establishes integrity, not trust: an attacker can hash their own hostile payload.

The reader parses the carrier in chunks, including capsules whose Base64 is on one long line. Decoded XZ bytes are counted and hashed while written to a temporary file. Only after the hash matches does decompression begin. Expanded TAR bytes are written to another temporary file with a running size check; decoding requests at most one byte beyond the remaining ceiling to detect excess. Normal I/O chunks are at most 1 MiB. The LZMA decoder has a separate memory limit.

Member count is checked as TAR entries are iterated. Oversized metadata reads are rejected before allocation by the TAR reader. The reader accepts one complete XZ stream and rejects incomplete streams, additional streams, and trailing compressed-payload data. ASCII whitespace is accepted within Base64, including across chunk boundaries; extra envelope content and duplicate markers are rejected.

**These ceilings are not a hard process-memory budget.** Large payload intermediates live on disk, but the compressor/decoder and the index of paths, TAR members, and manifest records still use RAM. Metadata memory grows with file count and path lengths. Preset 9 packing can consume substantial compressor memory even with chunked I/O; `--preset 6` offers a lower-memory option. Use an isolated process with external memory and disk quotas for untrusted capsules, and lower receiver ceilings for constrained sandboxes.

Temporary space must accommodate the compressed payload and expanded TAR, and later the TAR plus staged output. Packing self-verification may also retain its compressed intermediate alongside these files. Files are validated before publication. Existing output is preserved when capsule verification or extraction staging fails; replacement occurs only after the new capsule verifies or extraction staging succeeds. Temporary files and staging directories are cleaned up through context managers and `finally` blocks on handled failures. Abrupt process termination can still leave staging directories. This is disk-backed processing with multiple validation passes, not a one-pass network stream.

High compression ratio alone is not classified as an attack: repetitive text can compress extremely well. The current implementation uses absolute size checks rather than a ratio threshold. It does not guarantee safe processing up to the published maxima on every machine.
