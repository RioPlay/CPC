# CPC Conformance Requirements

## Reader MUST
- identify CPC by content, not filename extension alone;
- parse exactly one CPC block;
- strict-decode Base64 after removing allowed whitespace;
- verify payload SHA-256;
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

## Lifecycle implementation MUST additionally
- unpack into staging;
- atomically publish where practical;
- refuse silent overwrite;
- repack a fresh archive;
- preserve content ID for unchanged represented content;
- compare actual filesystem bytes/types against capsule state;
- maintain enough sidecar state to avoid relying on conversational memory.

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
