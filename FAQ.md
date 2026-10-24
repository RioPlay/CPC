# CPC FAQ

## Does CPC increase an LLM's context window?

No. CPC preserves project state in the sandbox so the LLM can inspect only what it needs.

## Why Markdown?

Markdown is broadly accepted by chat and LLM file-upload surfaces.

## Why Base64?

It turns the compressed binary archive into transport-safe text.

## What if an LLM returns a different or broken header?

Use `cpc returned.cpc.md` or `cpc u returned.cpc.md`. Basic restoration decodes
the single block between `<CPC>` and `</CPC>`, warns about missing/nonstandard
headers or unverified/mismatched hashes, and checks the full archive before
extracting. It never silently repacks an intended `.cpc.md` input. Unsafe,
ambiguous, incomplete or undecodable payloads still fail. `--strict` requires
the canonical header, matching sender hash and complete metadata audit. A
subsequent repack makes a new verified capsule, not proof of original integrity.

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

New packs also preserve file and directory modification times, subject to the receiving filesystem's range and precision. Use `--normalize-times` for compact/reproducible packaging when original dates are unnecessary. Repack remembers the selected policy when optional `--state` was saved; otherwise it uses current filesystem metadata and defaults. Old capsules cannot recover modification dates they never stored.

## Does a generated capsule inherit CPC's MIT license?

No. CPC's software license applies to CPC's source code. A capsule contains whatever content the user chooses to package.

## Do I need CPC installed?

No. Run `python bin/cpc.py` directly from the downloaded project. Other implementations can follow the [format specification](standard/SPEC.md).

## What if an LLM returns an archive that fails CPC validation?

Ordinary `cpc u` now accepts intact transport archives with defective optional metadata and warns. Use `--strict` to require the full audit, or `cpc recover returned.cpc.md -o new-recovery/` to retain original metadata and a diagnostic report separately. Recovery accepts missing or inconsistent CPC metadata, recreates implied directories, and keeps original paths beneath `new-recovery/files/`. It retains original metadata separately and writes a diagnostic report. It does not bypass unsafe paths, resource ceilings, or outer hash failures. `cpc r new-recovery/files/ -o repaired.cpc.md` creates and verifies fresh metadata from those recovered contents; it cannot prove the original project was complete.

## How should an LLM return edited work?

Use the supplied CLI's `handoff` command. It strictly verifies, compares the
selected source, and checks a clean restore before publishing the return folder.
Return every file in that folder: the capsule or all parts, `HANDOFF.md`, and
`VALIDATION.json`. Every export now supplies the runnable guide, including small
single-capsule exports. A bare `.cpc.md` still needs a reader; its compressed
payload does not replace an accessible packer. If Python, LZMA, the supplied
tool, or intact attachments are unavailable, report that limitation rather than
reconstructing a capsule by hand.

The report records packaging checks, not application-test success or authenticated
producer identity. Recipients should independently run strict verification.
Explicit `--project-name` and `--project-version` label a handoff; automatic
revision numbering and cross-chat coordination remain follow-up work.

## Who maintains CPC?

CPC was created and is maintained by RioPlay.
