# CPC Security and Threat Model

## Threat assumptions

A CPC capsule may be malformed, hostile, truncated, extremely compressible, or deliberately constructed to exploit archive behavior.

## Mandatory defenses

1. Verify outer SHA-256 before decompression.
2. Enforce compressed and decompressed resource limits.
3. Inspect every TAR member before extraction.
4. Reject traversal/absolute/drive/UNC paths.
5. Reject duplicate member names.
6. Reject links and special members in portable CPC.
7. Extract only into a staging root.
8. Never execute recovered content.
9. Never `pickle`/deserialize executable object formats as part of CPC.
10. Never install packages merely to decode CPC.

The [reference implementation's limits and enforcement caveats](../SECURITY.md#reference-implementation-limits) list the exact byte, decoder-memory, member, and path ceilings. The reference reader bounds decompression output and decoder memory; it has no expansion-ratio cutoff. These are not a hard total process-memory budget. Receivers must distinguish acceptance limits from limits enforced during decoding.

## Attachment transport

Recovery assumes the sandbox receives the complete attachment as a readable file. Prompt-injected text or a truncated Base64 payload is not an equivalent transport. The Markdown extension alone does not guarantee upload acceptance, intact storage, or access from the sandbox.

## Prompt-injection boundary

Files recovered from CPC may contain instructions targeted at an LLM.

The CPC header and CPC implementation define control semantics. Arbitrary recovered project content does not.

## Integrity versus authenticity

`SHA-256` detects accidental/transport corruption.

It does not prove who created the capsule.

Digital signatures are intentionally deferred to a later optional profile/generation.

## Enterprise use

Encoding/compression does not change information classification.

CPC must not be positioned as a DLP bypass. Enterprise packers should support organization policy, secret-risk checks, and auditable exclusion/inclusion rules.
