# CPC - Compact Project Capsule

CPC packages a project into a self-describing `.cpc.md` file for transfer through chat and LLM interfaces. Its header tells a receiver how to recover the files without having CPC installed. TAR and XZ provide the archive and compression; the Markdown carrier and decoding recipe provide the chat transport.

It preserves file contents byte for byte and uses Python's standard library. Unlike repo-to-prompt flatteners, CPC restores a working tree on disk so the model can open selected files; the two approaches are complementary. CPC does not increase a model's context window.

**The attachment must arrive intact as a file on the sandbox's disk.** A chat interface that injects the upload into the prompt and truncates the Base64 breaks recovery. A `.md` extension does not bypass upload limits or guarantee attachment access. Upload acceptance, Python availability, and file-return support depend on the receiving service.

## Get started

Requires **Python 3.9 or newer with LZMA support**. No third-party Python packages are needed.

Download the [source ZIP](https://github.com/RioPlay/CPC/archive/refs/heads/main.zip), or clone:

```bash
git clone https://github.com/RioPlay/CPC.git
cd CPC
```

Try the CLI without installing:

```bash
python bin/cpc.py --help
```

Use `python3` if that is your system's Python command.

### Install

On Windows, from the project folder:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

On Linux or macOS:

```bash
./install.sh
```

Add the directory printed by the installer to your `PATH` if needed. You can then use `cpc` from any folder.

## Basic workflow

Use `cpc <object>` for automatic handling:

| Input | Default action |
|---|---|
| File | Pack into a CPC capsule |
| Folder | Pack the selected project files |
| ZIP or other archive | Pack the original archive intact as an opaque file |
| Existing CPC capsule | Decode and unpack; `.cpc.md` always means an intended capsule, with content detection for other names |

Invalid CPC input is rejected; it is not silently wrapped in another capsule. Archives are not automatically expanded or converted. Explicit `p` and `u` commands remain available when you want to specify the operation.

Pack a project:

```bash
cpc Project/ -o Project.cpc.md
```

Add `--report` to see selected input bytes, final size, and the five largest included files:

```bash
cpc p Project/ -o Project.cpc.md --report
```

Verify the capsule and restore it into a separate folder:

```bash
cpc v Project.cpc.md
cpc u Project.cpc.md -o recovered/
```

After editing the restored files, create a new capsule:

```bash
cpc r recovered/Project/ -o Project-updated.cpc.md
```

For a chat handoff of CPC itself, download [CPC.cpc.md](https://github.com/RioPlay/CPC/raw/refs/heads/main/CPC.cpc.md).

### Return edited work

```bash
cpc export Project/ -o ../return-files
```

Upload the single `.cpc.md` in `return-files/` when it fits. Source exports now
run strict verification, source comparison and a clean restore comparison before
publication. No project commands or application tests are executed by packaging.
The receiving model gets the recovery tool and a concrete restore/return recipe
in that same attachment. See [one-file exports](#one-file-exports-for-chat).

For users who explicitly need filename/version labels and a separate audit
report, the earlier `cpc handoff` command remains available. That optional mode
produces `HANDOFF.md`, `VALIDATION.json` and the capsule/parts, and accepts
`--project-name NAME --project-version A.B.R`. It is not needed for ordinary
single-file transfers. Versions are explicit labels, not automatic allocation.

An expected full-carrier hash from another trusted channel can be checked using
`--expect-sha256 HEX` with verify, unpack or restore. Legacy separate guides use
this to reject pairing with the wrong capsule. A matching hash does not
establish sender identity. The self-contained file needs no separate guide.

### Recover CPC without installing it

Download only `CPC.cpc.md` and follow the instructions at its beginning. It now
includes the full receiver in compressed form and a small readable bootstrap.
The bootstrap recovers source for review; it never executes the receiver or
project. Python 3.9+ with LZMA is sufficient; no installation or network is needed.

Ordinary `pack`/`repack` and `export --bare` still produce minimal capsules without
this tool. Use normal `export` when the recipient needs a self-contained file.
Do not ask a model to invent an encoder or metadata. `bootstrap.py` in the project
installs launchers and is not needed for the attachment workflow.

### Commands

| Command | Action |
|---|---|
| `cpc` | Pack the current directory |
| `cpc <object>` | Auto-pack a file/folder or verify and unpack a CPC capsule |
| `cpc p <path>` | Pack a file or directory |
| `cpc u <capsule>` | Restore a capsule |
| `cpc recover <capsule> -o <new-directory>` | Explicitly recover safe archive contents despite defective CPC metadata |
| `cpc r <path>` | Repack a restored project |
| `cpc v <capsule>` | Verify integrity and archive structure |
| `cpc l <capsule>` | List contents |
| `cpc i <capsule>` | Inspect metadata |
| `cpc c <capsule> <path>` | Compare with local files |
| `cpc x <capsule> <member>` | Extract selected content |
| `cpc n <capsule> <name>` | Rename the logical root |
| `cpc export <source-or-capsule> -o <directory>` | Export one self-contained attachment, splitting only when required |
| `cpc restore <capsule> -o <new-directory>` | Strict restore, read-back and a workspace receipt |
| `cpc join <directory-or-parts...> -o <capsule>` | Verify and reconstruct a complete paired set |

Existing output is protected by default. Use `-f` to explicitly allow replacement or `-b` to back up existing output.
Export and join require a new destination and do not accept `-f` or `-b`.

Repack generates a fresh, strictly verified capsule from the current tree. It uses optional saved workflow settings when present; otherwise it uses normal packing defaults and filesystem metadata. No original capsule or state file is required. It does not reuse compressed data or create deltas. The implementation scope and follow-up are in [ROADMAP.md](ROADMAP.md).

### Basic restoration and replacement

Normal `u` and `v` decode exactly one payload between `<CPC>` and `</CPC>`. A missing, malformed or invented header does not block restoration when the Base64, complete single XZ stream and complete safe TAR are valid. Markdown titles/fences, leading blank lines and a UTF-8 BOM are tolerated outside the block. Header, hash and metadata warnings remain visible with `-q`. `v` reports `integrity=verified|unverified|mismatch` separately from `metadata=verified|unverified`. Only a canonical header, verified hash and successful metadata audit receive **PASS**. Other safely restorable input is reported as **RESTORABLE**, and unpack as **RESTORED**, even when its outer hash matches. A matching hash is consistency with a supplied digest, not authentication or proof of source completeness.

Custom CPC state and manifests are also optional for basic restoration. Missing, malformed or stale metadata produces a warning; the reader uses actual archive paths instead. Use `cpc v capsule.cpc.md --strict` or `cpc u capsule.cpc.md --strict` to require the canonical v1 header, a matching compressed-payload SHA-256 before decompression, and the full metadata audit. The reference packer always emits and strictly verifies canonical complete metadata, so its output remains readable by older CPC readers. Older readers may reject noncanonical input accepted by this broader reader profile. Ambiguous blocks, invalid Base64, incomplete/extra XZ streams, unsafe TARs and resource-limit violations remain errors in every mode.

Automatic handling never silently packs a file named `.cpc.md` into another `.cpc.md`: it attempts restoration and reports the actual decoding failure. For other filenames, content detection examines the first 64 KiB; use `cpc u <file>` explicitly if an unusually long preamble prevents automatic recognition. Headers never supply extraction paths. Review warnings before using recovered work; repacking creates a new strictly verified capsule, not retroactive verification of the incoming data.

Unpack writes project contents only by default. A folder capsule named `Project-v2.cpc.md` restores directly into `Project-v2/`, even if its archived folder was called `Project/`. Renaming the capsule gives each version a separate destination without nesting the old folder inside the new one. Both `cpc <capsule>` and `cpc u <capsule>` use this rule. The `.cpc.md` suffix is removed case-insensitively; other attachment names lose their last extension. Use `--original-root` to restore the archived folder name instead. Single-file capsules keep their actual filename and extension.

With one top-level file/folder, `-o` is its containing directory; missing explicit parent entries are created. Without `-o`, output goes beside the capsule. With multiple top-level items and no valid logical root, `-o` is required and names the exact destination containing all archived paths. Archive validation uses the stored paths before choosing the output folder. Reserved top-level `.cpc` records stay inside the input capsule; use `recover` if a separate evidence report is wanted.

For `updated.cpc.md` containing a project folder, these commands replace `C:\Work\updated` completely, removing obsolete files from the replacement:

```powershell
cpc u updated.cpc.md -o C:\Work -f
cpc u updated.cpc.md -o C:\Work -b
```

To replace the archived `Project/` instead, add `--original-root`. `cpc c <capsule> <folder>` compares project-relative contents, so an outer folder rename does not report every file as changed. Repacking records the current folder name in the new capsule.

Choose one: `-f` replaces; `-b` saves the old tree as `.bak`, `.bak1`, etc. Without either flag an existing destination is protected. Extraction is staged before replacement, and publication failure attempts to restore the previous tree. For multi-root archives the same flags affect the entire explicit `-o` directory. Hash mismatches, unsafe/ambiguous paths, unsupported types and resource violations remain errors, never metadata warnings.

On Windows, a scanner or another open handle can temporarily block the final directory rename. CPC retries Windows errors 5, 32 and 33 with at most 3.15 seconds of waiting per rename, including saving or restoring an existing destination. A persistent failure exits with `PUBLISH_FAILED` and prints the exact path of the completed extracted project, which is retained under `.cpc-stage-*` so you can open or copy it. If rollback also fails, CPC retains the previous project and prints its location too. These retained folders need manual cleanup after you recover the files. CPC does not disable security controls or fall back to copying a partial tree over your destination. Access denied alone does not identify the cause; a persistent permission or policy restriction requires another permitted destination or your administrator's help.

Optional `--state` writes an adjacent state file matching the output folder (for example `.updated.cpc-state`) for policy and Windows executable-intent continuity. When replacing a workspace with an older adjacent state file, use `--state` to refresh it, or move that old file aside; a clean restore refuses to silently leave stale state attached to a new tree.

### Recovering an improvised CPC from an LLM

Normal unpack can restore an intact LLM-produced archive despite defective custom metadata. Use explicit recovery when you also want to retain original metadata as separate evidence and write a diagnostic report:

```bash
cpc recover returned.cpc.md -o recovered-return/
cpc r recovered-return/files/ -o repaired.cpc.md
cpc v repaired.cpc.md
```

`recover` requires a new destination and never replaces the input or an existing project. It preserves all archived user paths under `recovered-return/files/`, including multiple top-level folders, and creates missing parent directories. It does not guess or strip a logical root. The original `.cpc` entries are retained byte-for-byte under `recovered-return/metadata/.cpc/` as evidence, separate from the recovered files. `recovery.json` records the outer hash, first CPC validation failure, counts, timestamp policy, and limitations. Recovery reports **CPC RECOVERED**, not **CPC PASS**; warnings remain visible with `-q`.

Fresh adjacent workspace state supports repacking `files/`, carrying TAR executable bits across Windows. It uses the archive profile; normal `.cpcignore` rules still apply during repack, so review exclusions. Recovery preserves recorded TAR modification times by default when CPC metadata cannot be verified. Implicit directories receive new dates. For unsupported or malformed dates, explicitly use `--normalize-times`. Valid original metadata can select its existing normalized timestamp policy, but defective metadata never supplies workspace paths or settings.

Recovery requires exactly one marker-delimited payload, valid Base64, a complete single XZ stream, and a complete safe TAR. Header/hash problems produce warnings and are recorded in `recovery.json`, including whether an outer hash was actually verified. It keeps all size/metadata/member limits and rejects unsafe paths, links, duplicate members, case collisions (including implied parents), file/directory conflicts, truncated members, and nonzero data after the TAR terminator. A stale inner file hash is recorded as a metadata failure; it is not evidence that the recovered file is correct. Recovery cannot prove original completeness or recreate files, dates, permissions, or policies that were never recorded. Repacking creates a new valid capsule from the recovered contents, not retroactive validation of the original.

### Modification times

New packs **preserve file and directory modification times by default**, including fractional seconds. Restore applies dates in staging before publication. Repack uses current filesystem dates, inheriting saved policy only when optional adjacent state exists. Restored-source export also inherits optional state; exporting an existing capsule keeps its compressed project payload intact. Without state, repack/export use preservation by default; select normalization explicitly when needed.

For a smaller, timestamp-independent capsule, explicitly choose normalization:

```bash
cpc p Project/ -o Project.cpc.md --normalize-times
cpc u Project.cpc.md -o recovered/ --state
cpc r recovered/Project/ -o Project-updated.cpc.md
```

Repack retains the workspace's saved policy. Use `--preserve-times` on pack/repack/source export to explicitly select preservation. `cpc i <capsule>` reports `mtime: preserve` or `mtime: normalize`. Normalization stores zero archive dates and restores files with fresh filesystem dates; it can change timestamp-dependent build or synchronization behavior.

The original file bytes remain exact, but timestamp precision and supported date ranges depend on the destination filesystem. Coarser filesystems can lose fractional precision. If applying a supported capsule date is denied or unsupported, CPC reports `TIMESTAMP_RESTORE_FAILED` before replacing the destination. An explicit `cpc u <capsule> --normalize-times` restores without original dates; add `--state` to remember that choice for future repacks.

Older capsules and sidecars without a timestamp policy keep their previous normalized behavior. They cannot recover original dates that were never recorded. The v1 header and TAR/XZ/Base64 chain are unchanged; older CPC tools can read new capsules but do not preserve their dates, so use this updated CLI throughout the handoff. Content IDs and `cpc c` compare file contents, paths, types, and executable intent, not timestamps. Preserved timestamps can change capsule bytes without changing content identity. Creation/access times, ownership and ACLs are not preserved.

Preserving dates adds per-file metadata. The cost depends on file count and timestamp variation; fractional times also add TAR extension records and temporary disk usage. XZ preset 6 and all resource limits remain unchanged.

### Executable permissions across operating systems

`cpc u <capsule> --state` records each file's executable intent in the adjacent `.cpc-state` sidecar. This is opt-in. Keep that sidecar with the workspace to preserve those flags across Windows repacks, including content edits at the same paths. New or renamed files use normal executable-file detection. Without state, Windows cannot reliably retain Unix executable intent. Linux and macOS filesystem permissions take precedence, so intentional `chmod` changes are retained.

This preserves CPC's executable/non-executable distinction, not full Unix modes, ownership, ACLs, or extended attributes. Existing sidecars remain readable; unpack an older capsule again with `--state` to create executable metadata if its sidecar lacks it.

The optional workspace sidecar and the capsule's internal metadata serve different purposes. A returned capsule carries its own fresh manifest and state. Missing local state never prevents repacking; it only means unavailable policy and executable information cannot be carried forward automatically.

Before returning edited work, use the supplied CLI to repack, verify with `--strict`, compare with the edited tree, and restore into a new test directory. Require successful exits and `CPC EQUAL` from compare; investigate exclusions if they cause a mismatch. The multipart guide includes these return steps. A matching hash establishes consistency with the hashed bytes, not whether the sender included every intended file or whether the sender is authentic.

### Memory and compression

Packing streams TAR data into XZ and stores the compressed intermediate in a temporary file, then writes Base64 in chunks. Recovery decodes to a temporary XZ file, checks its hash, and decompresses to a temporary TAR before validation and staged extraction. The wire format is unchanged; existing capsules remain readable.

Large payloads no longer need to fit in RAM. Compressor/decoder memory and the file/manifest index still consume memory, so this is not a fixed total-memory guarantee. Temporary disk space is required for compressed and expanded data, plus staged extraction. Temporary intermediates are cleaned up on normal completion and handled errors, except completed extractions retained after publication failure as described above. A terminated process or power loss can leave staging files behind.

The compression default is **XZ preset 6**, using Python's single-threaded incremental encoder. Use `--preset 9` for higher compression effort, or `-m` for preset 9 with extreme effort. Presets can change output size and runtime; file contents and the CPC format are unchanged. `--preset` and `-m` are mutually exclusive.

```bash
cpc p Project/ -o Project.cpc.md --preset 6 --report
```

Use `python tools/profile_resources.py` to compare presets on temporary synthetic text and binary inputs. It reports elapsed time, peak process resident memory, and final size in fresh subprocesses. An optional `--baseline PATH` compares another trusted version of `cpc.py`. No generated corpus or result file is included in the project capsule.

### One-file exports for chat

Use the normal export command:

```bash
cpc export Project/ -o ../Project-export
```

When it fits, upload **the single `.cpc.md` file**. It includes concise directions,
a readable bootstrap, the full recovery tool in compressed form, and the complete
project payload. No separate guide, CPC installation, network, or prior chat is
needed. The receiving model still needs Python execution and the original file.

The bootstrap only recovers tool source into a new `cpc-tools` directory. Review
that source before executing it. The next command performs strict verification,
staged restoration, and filesystem read-back without running project code:

```bash
python -I cpc-tools/cpc-recover.py restore input.cpc.md -o restored
```

It prints the exact workspace path and writes `restored/RESTORE.json`. The receipt
records content identity, regular-file count, verification results and the path to
saved policy/executable metadata. Existing destinations are never overwritten.
After editing, export the workspace named in the receipt to return one complete
attachment again. Tool/receipt files stay outside the project.

The default per-file limit is **25 MB (25,000,000 bytes)**. Change it when needed:

```bash
cpc export Project.cpc.md -o ../Project-export-small --max-file-size 10MB
```

If the complete attachment cannot fit, export emits `HANDOFF.md` and numbered
`.cpcpart.md` attachments. Upload every file. The guide carries the tool once;
parts contain only the capsule. Joining rejects missing, mixed, duplicate or
corrupted parts. The guide itself must fit the limit or nothing is published.
Splitting solves a per-file cap, not a total-size or context-window limit.

Source exports honor selection, compression and timestamp settings. Existing
capsule exports keep the compressed project payload unchanged, replace any old
wrapper, and require strict input integrity. Repeated export does not accumulate
recovery tools. The destination must be new and outside the source folder.

For a recipient who already has CPC, `--bare` preserves the previous export
behavior, including exact carrier-byte copies and the older multipart guide:

```bash
cpc export Project.cpc.md -o ../Project-bare --bare
```

Ordinary pack/repack still produce minimal v1 capsules. Old v1 readers can read the
new self-contained wrappers; the core Base64/XZ/TAR envelope has not changed.
See [the optional recovery wrapper](standard/SPEC.md#optional-self-contained-recovery-wrapper).


### File selection

Measured transfer sizes and the limited small-model trials are recorded in
[TRANSFER_VALIDATION.md](TRANSFER_VALIDATION.md).

The default chat profile skips common generated files such as `.git/` and `__pycache__/`, and applies patterns in the project's `.cpcignore`.

- `-a` uses archive mode, including supported files without automatic chat exclusions or `.cpcignore` filtering.
- `--include GLOB` overrides automatic exclusions and `.cpcignore`.
- `--exclude GLOB` takes precedence over inclusion.

Review capsule contents with `cpc l` before sharing. CPC does not detect secrets or decide which project files are appropriate to publish.

For text-focused chat handoffs, explicitly exclude unnecessary media, archives, and build output in your project's `.cpcignore`, for example:

```text
assets
dist
*.png
*.jpg
*.mp4
*.whl
*.zip
```

Keep assets that the task actually needs. The default profile does not silently exclude these file types. Filtering changes which files are carried, not the bytes of the files selected.

### Size tradeoff

Base64 takes four characters per three input bytes, plus padding. XZ can offset that overhead on source, notes, and logs; already-compressed PNGs, wheels, archives, and media often grow instead.

For a reproducible example, `python tools/measure_sizes.py` measures CPC's Python source and tests, then adds a ZIP containing 1 MiB of deterministic pseudorandom bytes. This illustrates source-heavy versus asset-heavy input; it is not a representative benchmark of all repositories. Both rows include all files without filtering.

| Input | File bytes before packing | Final `.cpc.md` bytes | Output / input |
|---|---:|---:|---:|
| CPC Python source and tests | 198,122 | 54,685 | 27.6% |
| Same source plus compressed asset | 1,247,136 | 1,455,065 | 116.7% |

Measured on Python 3.13 with this source revision. Sizes vary with source contents, source modification times and the LZMA runtime. The fixture retains source file dates and derives synthetic directory dates from their contents, so temporary staging time does not affect repeated measurements. Generated fixtures stay in a temporary directory. Check the final capsule size against the receiving interface's upload cap.

## Format and limitations

```text
#CPC|1|b64>xz>tar|<sha256-of-xz>
<CPC>
BASE64_PAYLOAD
</CPC>
```

The payload decodes through Base64, XZ, and TAR. SHA-256 detects corruption; it does not authenticate the sender or encrypt the files.

The decoding primitives are `base64`, `hashlib`, `lzma`, and `tarfile` from Python's standard library. A safe receiver must additionally enforce limits, validate all paths and member types, reject duplicates and links, and stage files before publishing them. A short decode-and-`extractall` snippet is not a safe receiver. See the [security model](standard/SECURITY.md) and [reference limits](SECURITY.md#reference-implementation-limits).

CPC supports regular files and directories, with portable path checks and extraction limits. Symlinks and special files are unsupported. It is not a full filesystem backup format, and Base64 overhead can make incompressible input larger. Large capsules also require memory for decoding.

## Documentation

- [FAQ](FAQ.md)
- [Format specification and conformance](standard/README.md)
- [Security policy](SECURITY.md)
- [Contribution policy](CONTRIBUTING.md)
- [Project governance](GOVERNANCE.md)

## Development

Run the regression suite:

```bash
python tests/test_cpc.py
python tests/test_security.py
python tests/test_streaming.py
python tests/test_export.py
python tests/test_transfer.py
python tests/test_handoff.py
```

Build the distributable project capsule from its explicit file list:

```bash
python tools/build_capsule.py
```

The builder packages only the listed source, documentation, and tests. It does not package the entire working directory. `python tools/build_capsule.py --check` verifies the existing capsule's integrity, file list, and file bytes against the working source without rebuilding it; differing modification dates alone do not fail the check. CI runs this check and the regression suite on Windows, macOS, and Linux with Python 3.9, 3.11, 3.13, and 3.14.

Git attributes keep text checkouts consistent across platforms: LF by default,
with CRLF for PowerShell scripts. Build release capsules from a Git checkout so
these declared working-tree line endings are applied.

## Status and license

Tooling version: **0.3.0-rc.8**. Canonical writer wire version: **1**. The format specification remains a draft.

Created and maintained by **RioPlay**. Released under the [MIT License](LICENSE).
