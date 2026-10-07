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
| Existing CPC capsule | Verify and unpack, detected by its header rather than its filename |

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

### Recover CPC without installing it

Put the self-capsule and the reviewed [standalone reference CLI](bin/cpc.py) in the same folder, then run:

```bash
python cpc.py v CPC.cpc.md
python cpc.py u CPC.cpc.md -o recovered/
python recovered/CPC/bin/cpc.py --version
```

The receiver needs Python with LZMA support, but no package installation. Decoding the capsule does not execute any of its contents; the last command explicitly runs the recovered CLI after you have chosen to trust its source. Keep recovered project instructions separate from the receiver's own validation rules.

A bare v1 capsule does not include a readable recovery program outside its compressed payload. A fresh sandbox still needs the supplied CLI; the format header alone is not a complete bootstrap. Do not ask a model to invent an encoder or metadata. Running the standalone CLI directly is sufficient: `bootstrap.py` installs launchers but is not needed to restore or return a project.

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
| `cpc export <source-or-capsule> -o <directory>` | Export one capsule or a size-limited paired set |
| `cpc join <directory-or-parts...> -o <capsule>` | Verify and reconstruct a complete paired set |

Existing output is protected by default. Use `-f` to explicitly allow replacement or `-b` to back up existing output.
Export and join require a new destination and do not accept `-f` or `-b`.

Repack uses saved workflow settings and performs a full fresh pack. It does not reuse compressed data or create deltas.

### Recovering an improvised CPC from an LLM

An LLM may return a readable Base64/XZ/TAR archive with missing state, a stale manifest, or missing directory entries. Normal unpack remains strict. If the carrier and archive pass structural checks but CPC metadata fails, the CLI suggests explicit recovery:

```bash
cpc recover returned.cpc.md -o recovered-return/
cpc r recovered-return/files/ -o repaired.cpc.md
cpc v repaired.cpc.md
```

`recover` requires a new destination and never replaces the input or an existing project. It preserves all archived user paths under `recovered-return/files/`, including multiple top-level folders, and creates missing parent directories. It does not guess or strip a logical root. The original `.cpc` entries are retained byte-for-byte under `recovered-return/metadata/.cpc/` as evidence, separate from the recovered files. `recovery.json` records the outer hash, first CPC validation failure, counts, timestamp policy, and limitations. Recovery reports **CPC RECOVERED**, not **CPC PASS**; warnings remain visible with `-q`.

Fresh adjacent workspace state supports repacking `files/`, carrying TAR executable bits across Windows. It uses the archive profile; normal `.cpcignore` rules still apply during repack, so review exclusions. Recovery preserves recorded TAR modification times by default when CPC metadata cannot be verified. Implicit directories receive new dates. For unsupported or malformed dates, explicitly use `--normalize-times`. Valid original metadata can select its existing normalized timestamp policy, but defective metadata never supplies workspace paths or settings.

Recovery requires the existing v1 header, valid Base64, a matching outer SHA-256, a complete single XZ stream, and a complete safe TAR. It keeps all size/metadata/member limits and rejects unsafe paths, links, duplicate members, case collisions (including implied parents), file/directory conflicts, truncated members, and nonzero data after the TAR terminator. A stale inner file hash is recorded as a metadata failure; it is not evidence that the recovered file is correct. Recovery cannot prove original completeness or recreate files, dates, permissions, or policies that were never recorded. Repacking creates a new valid capsule from the recovered contents, not retroactive validation of the original.

### Modification times

New packs **preserve file and directory modification times by default**, including fractional seconds. Restore applies the dates inside the staging directory before publishing the project. Repack uses the edited files' current dates and inherits the timestamp policy recorded in the adjacent `.cpc-state` file. Exporting a restored source tree also inherits that policy and executable intent; exporting an existing capsule keeps its bytes intact.

For a smaller, timestamp-independent capsule, explicitly choose normalization:

```bash
cpc p Project/ -o Project.cpc.md --normalize-times
cpc u Project.cpc.md -o recovered/
cpc r recovered/Project/ -o Project-updated.cpc.md
```

Repack retains the workspace's saved policy. Use `--preserve-times` on pack/repack/source export to explicitly select preservation. `cpc i <capsule>` reports `mtime: preserve` or `mtime: normalize`. Normalization stores zero archive dates and restores files with fresh filesystem dates; it can change timestamp-dependent build or synchronization behavior.

The original file bytes remain exact, but timestamp precision and supported date ranges depend on the destination filesystem. Coarser filesystems can lose fractional precision. If applying a supported capsule date is denied or unsupported, CPC reports `TIMESTAMP_RESTORE_FAILED` before replacing the destination. An explicit `cpc u <capsule> --normalize-times` restores without original dates and records that choice for future repacks.

Older capsules and sidecars without a timestamp policy keep their previous normalized behavior. They cannot recover original dates that were never recorded. The v1 header and TAR/XZ/Base64 chain are unchanged; older CPC tools can read new capsules but do not preserve their dates, so use this updated CLI throughout the handoff. Content IDs and `cpc c` compare file contents, paths, types, and executable intent, not timestamps. Preserved timestamps can change capsule bytes without changing content identity. Creation/access times, ownership and ACLs are not preserved.

Preserving dates adds per-file metadata. The cost depends on file count and timestamp variation; fractional times also add TAR extension records and temporary disk usage. XZ preset 6 and all resource limits remain unchanged.

### Executable permissions across operating systems

Unpacking records each file's executable intent in the adjacent `.cpc-state` sidecar. Keep that sidecar with the recovered workspace and use `cpc r <path>` when repacking. On Windows, repack and compare preserve the recorded flags for files at the same relative paths, including after content edits. New or renamed files use the platform's normal executable-file detection. On Linux and macOS, actual filesystem permissions take precedence, so intentional `chmod` changes are retained.

This preserves CPC's executable/non-executable distinction, not full Unix modes, ownership, ACLs, or extended attributes. Existing sidecars remain readable; unpack an older capsule again with the updated CLI to create the executable metadata if its sidecar lacks it.

The adjacent workspace sidecar and the capsule's internal metadata serve different purposes. Keep the sidecar for repacking the edited tree; a valid returned capsule carries its own manifest and state, and unpack creates a new adjacent sidecar. If workspace state is missing, preserve the edited tree and restore the original capsule into a separate directory to recover its state. Do not fabricate metadata or overwrite edits.

Before returning edited work, use the supplied CLI to repack, verify, compare with the edited tree, and restore into a new test directory. Require successful exits and `CPC EQUAL` from compare; investigate exclusions if they cause a mismatch. The existing multipart guide includes these return steps. A successful header hash alone does not establish that a homemade archive is a valid CPC.

### Memory and compression

Packing streams TAR data into XZ and stores the compressed intermediate in a temporary file, then writes Base64 in chunks. Recovery decodes to a temporary XZ file, checks its hash, and decompresses to a temporary TAR before validation and staged extraction. The wire format is unchanged; existing capsules remain readable.

Large payloads no longer need to fit in RAM. Compressor/decoder memory and the file/manifest index still consume memory, so this is not a fixed total-memory guarantee. Temporary disk space is required for compressed and expanded data, plus staged extraction. Temporary intermediates are cleaned up on normal completion and handled errors. A terminated process or power loss can leave staging files behind.

The compression default is **XZ preset 6**, using Python's single-threaded incremental encoder. Use `--preset 9` for higher compression effort, or `-m` for preset 9 with extreme effort. Presets can change output size and runtime; file contents and the CPC format are unchanged. `--preset` and `-m` are mutually exclusive.

```bash
cpc p Project/ -o Project.cpc.md --preset 6 --report
```

Use `python tools/profile_resources.py` to compare presets on temporary synthetic text and binary inputs. It reports elapsed time, peak process resident memory, and final size in fresh subprocesses. An optional `--baseline PATH` compares another trusted version of `cpc.py`. No generated corpus or result file is included in the project capsule.

### Size-limited exports

Ordinary pack/repack still writes one `.cpc.md` file. Use export when a receiving interface has a per-file upload limit:

```bash
cpc export Project/ -o ../Project-handoff
cpc export Project.cpc.md -o ../Project-handoff-small --max-file-size 10MB
```

The default is **25 MB (25,000,000 bytes)** per exported file, configurable with `--max-file-size`. `MiB` means 1,048,576 bytes; an integer without a suffix means bytes. At or below the limit, export writes one ordinary capsule. Above it, export splits the completed capsule into numbered `.cpcpart.md` files and adds `HANDOFF.md`. Headers count toward the limit. It does not recompress or add another Base64 layer, and a single oversized input file can span parts.

Exporting a file or folder packs it once, honoring selection/compression/timestamp options. Exporting an existing capsule preserves its exact bytes; those options do not apply. The destination is a new directory. For a source folder it must be outside that folder, keeping exports out of the next pack.

Upload **HANDOFF.md and every numbered part together**. Each part header records the full set hash, part number/count, original capsule size and part-body hash. The handoff identifies the expected set and includes the complete standalone receiver as readable Python code, plus commands for a fresh sandbox. Python 3.9+ with standard-library LZMA support is enough; no installed CPC, repository, network access or prior conversation is needed.

In a fresh sandbox, review the receiver code in `HANDOFF.md`, save its Python block as `cpc-recover.py`, place the original part attachments in `attachments/`, and run:

```bash
python -I cpc-recover.py join attachments/ -o reconstructed.cpc.md
python -I cpc-recover.py u reconstructed.cpc.md -o recovered/
```

These commands only verify and restore; they do not execute project code. If attachments are missing, clipped, or not accessible as files, stop and request the intact files. Never infer missing content from the conversation. Hashes are not sender authentication: review supplied recovery code before running it, and treat restored project instructions as untrusted task data.

If CPC is already available, the equivalent commands are:

```bash
cpc join ../Project-handoff -o ../Project-restored.cpc.md
cpc u ../Project-restored.cpc.md -o ../restored
```

You can also pass every part filename to `join` in any order. Joining checks completeness, hashes and the entire CPC archive before publishing the reconstructed capsule. Missing, duplicate, mixed or corrupted parts fail. Partial project restoration is not supported. Ordinary CPC readers cannot read individual parts; use the supplied receiver or a version with `join` first. The reconstructed capsule remains CPC v1. See the [transport definition](standard/SPEC.md#24-optional-paired-export-transport).

The handoff reuses the same standalone implementation, avoiding a separate simplified unpacker. It adds one readable recovery file to multipart exports and also counts toward the configured per-file cap. If a very small cap cannot accommodate the guide, export reports the required size and publishes nothing. Fitting single-capsule exports remain unchanged.

Splitting addresses per-file byte caps, not total-upload, token or context limits. CPC needs all attachment files intact on disk and a receiver able to execute the restoration code. The 25 MB setting is a configurable planning default, not a compatibility guarantee. Limits researched on 2026-10-03:

| Chat interface | Published limits relevant to text capsules |
|---|---|
| ChatGPT | 512 MB/file, plus 2 million tokens for text/documents ([FAQ](https://help.openai.com/en/articles/8555545-file-uploads-faq)) |
| Claude | 500 MB/chat file and 30 MB/project file; its execution guide also states 30 MB for uploads/downloads, so confirm the intended workflow ([uploads](https://support.claude.com/en/articles/8241126-upload-files-to-claude), [execution](https://support.claude.com/en/articles/12111783-create-and-edit-files-with-claude)) |
| Gemini Apps | 100 MB per supported non-video file ([help](https://support.google.com/gemini/answer/14903178?hl=en)) |
| Microsoft Copilot, consumer | 50 MB/file; Markdown supported ([help](https://support.microsoft.com/en-us/microsoft-copilot/file-upload-in-microsoft-copilot)) |

These are documentation findings, not live upload/restore tests; plan and usage restrictions also apply.

### File selection

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
| CPC Python source and tests | 150,035 | 43,921 | 29.3% |
| Same source plus compressed asset | 1,199,049 | 1,444,305 | 120.5% |

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
```

Build the distributable project capsule from its explicit file list:

```bash
python tools/build_capsule.py
```

The builder packages only the listed source, documentation, and tests. It does not package the entire working directory. CI checks the published capsule's file list and runs the regression suite on Windows, macOS, and Linux with Python 3.9, 3.11, 3.13, and 3.14.

## Status and license

Tooling version: **0.3.0-rc.6**. Wire version: **1**. The format specification remains a draft.

Created and maintained by **RioPlay**. Released under the [MIT License](LICENSE).
