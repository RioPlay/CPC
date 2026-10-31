# Compact transfer validation

Scope: the 0.3.0-rc.8 candidate, tested on Linux with Python 3.12.14.
Cross-platform regressions run in the repository's CI matrix. This record does
not establish universal model or platform compatibility.

## Size and compatibility

The existing portable skills delivery contained 47 files with 76,519 bytes of
file contents. Its rc.7 capsule and separate recovery guide totaled 130,113
bytes. The rc.8 self-contained export of the same capsule is 76,000 bytes: one
attachment and a 41.59% reduction in complete delivery size. This compares the
actual previous delivery with the new tool, not only compressed payloads.

The project payload was retained unchanged. All 47 project files matched the
source, and the previous rc.7 CLI passed strict verification of the new wrapper.
The difference includes a newer, larger receiver with the added restore command;
no file was summarized, omitted or minified to produce this saving.

## Small-model trials

Three fresh GPT-6 Luna sessions, medium reasoning, received a synthetic Python
project attachment and a task. They had no parent conversation history. Their
scope was restricted to the supplied directory with no network sources. This
was an early rc.8 candidate before the upload-cap fix, help-text clarification and reconciliation of the
existing validated-handoff PR; automated checks also cover the integrated version.

1. **Restore, edit, return:** accept case-insensitive temperature unit labels,
   preserve formatting, reject unsupported labels, update tests and return CPC.
   Luna restored the attachment, passed three test methods and returned one
   self-contained capsule. A separate harness restored its output and passed
   16 behavior checks, verified unrelated file hashes and the empty directory.
   Luna reported one help lookup before export; no additional user guidance was
   supplied. Running tests added Python bytecode caches to this include-all
   fixture; those extra files were present in the returned archive.
2. **Damaged attachment:** the project payload had one altered encoded byte;
   the bundled receiver remained intact. Luna reported `HASH_MISMATCH`, stopped
   restoration, and did not invent project details or a restored file count.

A third fresh session repeated the edit/return task against the integrated
candidate. It passed three test methods and returned one self-contained capsule.
The parent again checked 16 behavior cases and unrelated-file preservation.
Luna initially ran tests from the parent directory, received an import error,
and corrected the working directory itself. The final source adds only a further
concurrent-payload-change guard after this trial; automated regressions cover it.

These are functional observations, not a controlled model-quality benchmark.
There was no matched two-file baseline or statistical repeated sampling. The parent assistant
designed the fixture, implemented the feature and evaluated the output, so the
evaluation is not independent of development. No comparative speed or token-cost
claim is made. Broader model testing should include larger projects, multipart
uploads and environments with different attachment and execution capabilities.

## Automated checks

`tests/test_transfer.py` follows the attachment's bootstrap in isolated Python
processes, verifies the exact recovered CLI source, and covers cold restoration,
editing and return, re-export without wrapper accumulation, payload corruption,
receiver corruption, decoder limits, trailing XZ streams, no receiver execution,
refusal to overwrite, read-back failure, opaque files and upload-cap boundaries.
The existing archive-safety, recovery, timestamp, transport, release and export
regressions remain part of CI. Release checks also reject stale receiver footers.
