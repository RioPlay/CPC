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
| Expansion ratio | No ratio limit is implemented |

SHA-256 is checked on the compressed bytes before decompression. A matching hash establishes integrity, not trust: an attacker can hash their own hostile payload.

The reader bounds carrier reads, checks the Base64 length before decoding, and caps decompression output at the TAR ceiling plus one detection byte. The LZMA decoder has a separate memory limit. Member count is checked as TAR entries are iterated. The reader accepts one complete XZ stream and rejects incomplete streams, additional streams, and trailing compressed-payload data.

**These ceilings are not a hard process-memory budget.** Carrier text, compressed bytes, expanded TAR data, and parsed metadata can coexist in memory. TAR parsing also has its own allocations. Use an isolated process with an external memory limit for untrusted capsules, and lower receiver ceilings for constrained sandboxes. The implementation is bounded during decoding but is not a streaming extractor.

High compression ratio alone is not classified as an attack: repetitive text can compress extremely well. The current implementation uses absolute size checks rather than a ratio threshold. It does not guarantee safe processing up to the published maxima on every machine.
