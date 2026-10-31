# CPC Conformance Requirements

## Reader MUST
- validate CPC by payload content; capsule-shaped filenames indicate restore intent, never automatic repacking;
- parse exactly one CPC block;
- strict-decode Base64 after removing allowed whitespace;
- compute payload SHA-256 and truthfully report verified, unverified or mismatched sender integrity;
- decompress XZ/LZMA2;
- parse TAR;
- validate all member paths before publication;
- reject duplicate member paths;
- reject unsupported member types;
- enforce resource ceilings;
- recover exact regular-file bytes;
- preserve empty directories where represented;
- fail closed.

## Writer MUST
- emit canonical CPC header grammar;
- emit UTF-8 Markdown with LF;
- use standard Base64;
- use XZ/LZMA2;
- produce a safe TAR;
- normalize nonessential metadata;
- deterministically order members;
- preserve file bytes;
- reject unsupported portable names/types;
- verify its own generated capsule before success.
- fail on source enumeration/read errors rather than silently omit unreadable selected files or directories.

## Lifecycle implementation MUST additionally
- unpack into staging;
- atomically publish where practical;
- refuse silent overwrite;
- repack a fresh archive;
- preserve content ID for unchanged represented content;
- compare actual filesystem bytes/types against capsule state;
- work without a sidecar, with optional state for settings the filesystem cannot retain.

Basic readers MUST retain transport and archive-safety checks while treating
headers, supplied hashes and custom CPC metadata as advisory. They MUST warn
when a header is absent/nonstandard, a hash is missing/ambiguous/mismatched, or an audit fails and MUST
NOT let unverified state control extraction paths. Full-audit readers additionally
require a canonical header, matching compressed hash before decompression,
and the internal state and manifest. Reference writers still emit and
strictly verify full-profile output. A matching hash does not establish that
the sender selected every intended file or authenticate the sender.

The reference CLI reserves PASS for a canonical header, verified sender hash and
complete metadata audit together. Safely restorable basic input with missing or
defective metadata MUST NOT receive that full-profile status. The handoff
lifecycle publishes only after strict validation, selected-source comparison and
a matching clean restore. Its report must distinguish packaging checks from
application checks and cannot authenticate the producer.

The reference reader also supports an externally supplied complete-carrier
SHA-256. It hashes the same bytes it decodes and rejects a mismatched expected
identity before decompression, even if the incoming capsule is otherwise valid.
This additional check does not replace the full audit or authenticate a sender.

## Recommended status vocabulary

```text
PASS
FAIL
UNKNOWN
```

Suggested stable machine error codes:

```text
NOT_CPC
UNSUPPORTED_CPC
INVALID_HEADER
INVALID_MARKERS
BAD_BASE64
HASH_MISMATCH
DECOMPRESSION_FAILED
BAD_TAR
UNSAFE_PATH
DUPLICATE_MEMBER
UNSUPPORTED_MEMBER_TYPE
RESOURCE_LIMIT
DEST_EXISTS
SOURCE_CHANGED
MANIFEST_MISMATCH
CONTENT_MISMATCH
```
