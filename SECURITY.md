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
