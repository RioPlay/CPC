# CPC round-trip portability roadmap

Goal: carry a small project from a local machine into an LLM sandbox, edit it,
return the same transport format, and restore the finished tree locally.

## This implementation

1. **Basic transport restoration.** Keep canonical v1 writer output and
   Base64/XZ/TAR, bounded decoding, safe paths and complete archive checks.
   Decode a single marker-delimited payload despite missing/invented headers,
   mismatched or unavailable hashes, and defective optional metadata, with
   explicit integrity warnings. `--strict` requires canonical header/hash and
   the full metadata audit.
2. **Predictable destinations.** Infer a single top-level file/folder from the
   actual archive if metadata is unavailable. Multiple roots require an
   explicit output directory and retain all paths. Default refuses overwrite;
   `-f` replaces the whole destination and `-b` saves it first. Stage before
   replacement; a failed restore must leave existing data intact.
3. **Clean, independent workspaces.** Ordinary unpack writes only project
   contents. Make adjacent workflow state opt-in with `--state`. Repack works
   without it and generates fresh, strictly verified metadata. Existing state
   remains usable when present, but is never required for a valid new pack.
   Explain the limits of carrying Unix executable flags through Windows and
   policy choices through a workspace with no state.
4. **Compatibility and proof.** Keep strict reference-packer output compatible
   with existing readers. Document the broader basic-reader profile (older
   readers still reject metadata-deficient input). Test malformed metadata,
   inferred folders, replacement, rollback, stateless round trips, legacy
   state, multipart transport and hostile/corrupted inputs. Refresh public
   docs, CI and the allowlisted self-capsule.

## Validated handoff draft (0.3.0-rc.8)

The first implementation slice adds `cpc handoff`: use the reference packer,
strictly validate, compare selected source contents, check a clean restore, and
publish a complete return directory only after those checks pass. Optional
`--project-name` and `--project-version` produce short explicit filename labels.
The command emits a hash-bound audit report and explicitly marks application
validation as not run. It is not signed producer attestation.

Every export now includes the runnable `HANDOFF.md`, whether the capsule fits
in one file or needs transport parts. Explicit CLI include/exclude rules travel
in optional metadata and `--state` workspaces; comparison and repack reuse them.
Basic recovery remains available, but incomplete metadata no longer receives a
standalone PASS status. The v1 wire envelope and codecs remain unchanged.

Review fixes halt source scanning on directory I/O errors and bind guide
verification/restoration to the expected complete-carrier hash. Regressions
cover an unreadable included directory that previously disappeared from a PASS
handoff, and a different valid capsule that must fail the expected identity
before decompression. Explicit exclusions remain permitted and reported.

Cold-directory tests cover restoring, editing and returning through only the
exported CLI for both sizes, with independent strict checks of the returned
artifact. This is not yet evidence that fresh LLM chats reliably follow the
guide, or that Windows/macOS have passed this draft's CI matrix.

## Separate follow-up

- Deterministic project-state change planning and automatic third-component
  revision allocation, excluding generated bookkeeping from change decisions.
- Baseline-aware completeness checks and a preflight explaining selection rules,
  required paths, and unexpected removals. Self-consistency alone does not prove
  that an edited project still contains every intended file.
- Stable project identity, parent checkpoints and guarded shared-head updates
  before multiple chats can allocate or promote versions concurrently.
- A resumable work contract and one real fresh-chat continuation before adding
  scheduled work. Keep source history in Git where already available.
- Cross-model handoff trials that record whether the supplied command was used,
  and independently validate the returned artifact rather than trusting prose.

A self-contained Markdown handoff with the actual packer and one return
command in the same single attachment remains a separate carrier-design task.
The current guide-plus-capsule bundle already supplies the runnable packer and
one return command without embedding executable instructions in the v1 carrier.
A combined carrier needs an explicit design/version and fresh-sandbox tests.
Keep splitting conditional on the complete export exceeding the configured limit.

No signatures, parent chains, deltas, new codecs or installation dependencies
are required for this milestone. Hashes establish consistency with the sent
bytes, not sender identity or whether the sender selected every intended file.

## Completion record

2026-10-13: payload-first decoding accepts supplementary header variations and
Markdown wrappers. Sender hash status is reported separately from inner metadata
and archive safety. Capsule filenames force restore intent instead of accidental
double-packing. Canonical writers and strict audits remain available. The new
header regression suite covers this behavior, chunk boundaries and rejection of
ambiguous/unsafe payloads; release tooling is now 0.3.0-rc.7.

Completed locally on 2026-10-07:

- Basic unpack/verify warn about defective metadata; `--strict` retains the
  full audit. The reference packer still emits strictly verified full metadata.
- Single roots are inferred from TAR paths; multiple roots require an explicit
  destination. Whole-tree replacement, numbered backups and failure rollback
  are covered by tests.
- Unpack is stateless by default; `--state` is opt-in. Repack works with or
  without legacy state. A stale adjacent sidecar must be refreshed or moved
  aside before stateless replacement.
- All seven suites passed on Windows/Python 3.13 and native Linux/Python 3.12.
  Basic transport, recovery and security suites also passed on Windows Python
  3.9, 3.11 and 3.14. The new basic suite includes 12 cases, including an edited
  stateless round trip, multiple roots, malicious metadata, overwrite/backup,
  publication rollback, optional state and multipart transport.
- No new runtime dependencies, codec changes, or automatic history tracking.
  The separate self-contained carrier above remains unimplemented.
