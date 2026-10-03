# CPC ? Compact Project Capsule

CPC packages a project into a `.cpc.md` file for transfer through chat and LLM interfaces. Restore the files in a compatible sandbox, continue working, and repack the project for the next handoff.

It preserves file contents byte for byte and uses Python's standard library. Upload acceptance, Python availability, and file-return support depend on the receiving service. CPC does not increase a model's context window.

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

Pack a project:

```bash
cpc p Project/ -o Project.cpc.md
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

### Commands

| Command | Action |
|---|---|
| `cpc` | Pack the current directory |
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

### File selection

The default chat profile skips common generated files such as `.git/` and `__pycache__/`, and applies patterns in the project's `.cpcignore`.

- `-a` uses archive mode, including supported files without automatic chat exclusions or `.cpcignore` filtering.
- `--include GLOB` overrides automatic exclusions and `.cpcignore`.
- `--exclude GLOB` takes precedence over inclusion.

Review capsule contents with `cpc l` before sharing. CPC does not detect secrets or decide which project files are appropriate to publish.

## Format and limitations

```text
#CPC|1|b64>xz>tar|<sha256-of-xz>
<CPC>
BASE64_PAYLOAD
</CPC>
```

The payload decodes through Base64, XZ, and TAR. SHA-256 detects corruption; it does not authenticate the sender or encrypt the files.

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
```

Build the distributable project capsule from its explicit file list:

```bash
python tools/build_capsule.py
```

The builder packages only the listed source, documentation, and tests. It does not package the entire working directory. CI checks the published capsule's file list and runs the regression suite on Windows, macOS, and Linux with Python 3.9, 3.11, and 3.13.

## Status and license

Tooling version: **0.3.0-rc.6**. Wire version: **1**. The format specification remains a draft.

Created and maintained by **RioPlay**. Released under the [MIT License](LICENSE).
