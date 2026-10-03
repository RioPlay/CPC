# CPC FAQ

## Does CPC increase an LLM's context window?

No. CPC preserves project state in the sandbox so the LLM can inspect only what it needs.

## Why Markdown?

Markdown is broadly accepted by chat and LLM file-upload surfaces.

## Why Base64?

It turns the compressed binary archive into transport-safe text.

## Why XZ/LZMA2?

Strong compression and long-standing Python standard-library support.

## Why TAR?

It is a mature filesystem container and keeps the decoder small.

## Why not ZIP?

ZIP is still useful. CPC is optimized for chat transport, self-description, filtering, recovery, and repacking.

## Can CPC carry ZIP files?

Yes. Nested archives are preserved as opaque bytes by default.

## Is CPC lossless?

File contents are byte-preserved. Archive mode includes every supported regular file/directory. CPC is not a full filesystem-backup format for ACLs, xattrs, device nodes, etc.

## Does a generated capsule inherit CPC's MIT license?

No. CPC's software license applies to CPC's source code. A capsule contains whatever content the user chooses to package.

## Do I need CPC installed?

No. Run `python bin/cpc.py` directly from the downloaded project. Other implementations can follow the [format specification](standard/SPEC.md).

## Who maintains CPC?

CPC was created and is maintained by RioPlay.
