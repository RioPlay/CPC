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

### Commands

| Command | Action |
|---|---|
| `cpc` | Pack the current directory |
| `cpc <object>` | Auto-pack a file/folder or verify and unpack a CPC capsule |
| `cpc p <path>` | Pack a file or directory |
| `cpc u <capsule>` | Restore a capsule |
| `cpc r <path>` | Repack a restored project |
| `cpc v <capsule>` | Verify integrity and archive structure |
| `cpc l <capsule>` | List contents |
| `cpc i <capsule>` | Inspect metadata |
| `cpc c <capsule> <path>` | Compare with local files |
| `cpc x <capsule> <member>` | Extract selected content |
| `cpc n <capsule> <name>` | Rename the logical root |

Existing output is protected by default. Use `-f` to explicitly allow replacement or `-b` to back up existing output.

Repack uses saved workflow settings and performs a full fresh pack. It does not reuse compressed data or create deltas.

### Memory and compression

Packing streams TAR data into XZ and stores the compressed intermediate in a temporary file, then writes Base64 in chunks. Recovery decodes to a temporary XZ file, checks its hash, and decompresses to a temporary TAR before validation and staged extraction. The wire format is unchanged; existing capsules remain readable.

Large payloads no longer need to fit in RAM. Compressor/decoder memory and the file/manifest index still consume memory, so this is not a fixed total-memory guarantee. Temporary disk space is required for compressed and expanded data, plus staged extraction. Temporary intermediates are cleaned up on normal completion and handled errors. A terminated process or power loss can leave staging files behind.

The compression default remains **XZ preset 9**. Use `--preset 6` to try a lower-memory compressor, or `-m` for preset 9 with extreme compression effort. Presets can change output size and runtime; file contents and the CPC format are unchanged. `--preset` and `-m` are mutually exclusive.

```bash
cpc p Project/ -o Project.cpc.md --preset 6 --report
```

Use `python tools/profile_resources.py` to compare presets on temporary synthetic text and binary inputs. It reports elapsed time, peak process resident memory, and final size in fresh subprocesses. An optional `--baseline PATH` compares another trusted version of `cpc.py`. No generated corpus or result file is included in the project capsule.

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
| CPC Python source and tests | 65,590 | 21,049 | 32.1% |
| Same source plus compressed asset | 1,114,604 | 1,421,369 | 127.5% |

Measured on Python 3.13 with this source revision. Sizes vary with source changes and the LZMA runtime. Generated fixtures stay in a temporary directory. Check the final capsule size against the receiving interface's upload cap.

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
```

Build the distributable project capsule from its explicit file list:

```bash
python tools/build_capsule.py
```

The builder packages only the listed source, documentation, and tests. It does not package the entire working directory. CI checks the published capsule's file list and runs the regression suite on Windows, macOS, and Linux with Python 3.9, 3.11, and 3.13.

## Status and license

Tooling version: **0.3.0-rc.6**. Wire version: **1**. The format specification remains a draft.

Created and maintained by **RioPlay**. Released under the [MIT License](LICENSE).
