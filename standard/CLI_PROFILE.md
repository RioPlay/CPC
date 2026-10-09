# CPC CLI Profile

The CLI is not part of the CPC wire grammar, but this profile standardizes the intended user experience.

## Minimal interactive surface

```text
cpc
cpc <thing>
cpc p <thing>
cpc u <capsule>
cpc recover <capsule> -o <new-directory> [--normalize-times]
cpc r <workspace>
cpc v <capsule>
cpc l <capsule>
cpc i <capsule>
cpc c <capsule> <thing>
cpc x <capsule> <member>
cpc n <capsule> <new-root>
cpc export <source-or-capsule> -o <new-directory> [--max-file-size 25MB]
cpc join <directory-or-parts...> -o <new-capsule>
```

Semantics:

```text
cpc
→ pack current directory

cpc normal-input
→ pack

cpc CPC-input
→ unpack
```

Short verbs:

```text
p pack
u unpack
r repack
v verify
l list
i inspect
c compare
x selective extract
n logical-root rename
```

Recommended core flags:

```text
-o PATH  output
-f       force/overwrite
-b       backup existing
-q       quiet
-V       verbose
--strict unpack/verify: require the full metadata audit
--state  unpack: save optional adjacent workflow state
-a       archive profile
-m       maximum compression effort
--preset N  XZ preset 0-9 (default 6; mutually exclusive with -m)
--original-root  unpack only: restore the archived folder name instead of the capsule filename
--normalize-times  discard original modification dates for compact/reproducible output
--preserve-times   preserve modification dates (new-pack default; repack inherits saved policy)
--report    selected bytes, output size, and largest included files
--max-file-size SIZE  export only, default 25MB (decimal); MiB also accepted
```

Outer filesystem copy/move/rename operations are intentionally not duplicated by CPC.

Normal `u` and `v` validate transport integrity and archive safety. Optional CPC metadata failures produce warnings, including with `-q`, and actual TAR paths determine restoration. `v` reports `metadata=verified|unverified`. `--strict` requires the complete metadata audit and applies only to unpack/verify (including implicit unpack). List, inspect, export and join also accept basic transport input; compare and root rename require full metadata. The reference packer always generates and strictly verifies fresh full metadata.

Ordinary unpack writes only project contents. `--state` opts into adjacent workflow state; it applies only to full unpack. Repack works without state using normal packing defaults and filesystem metadata. For a single top-level item, `-o` is the containing directory. Multiple roots require `-o` naming the exact destination. `-f` replaces that entire destination; `-b` keeps its previous contents in a numbered backup. Neither merges old and new files. With neither flag existing output is protected. A preexisting adjacent state file requires `--state` to refresh it or moving it aside before a stateless restore.

Full folder unpack (explicit or implicit) uses the capsule filename for the output folder: `Project-v2.cpc.md` becomes `Project-v2/`, stripping `.cpc.md` case-insensitively or otherwise the last extension. The archived root folder is published directly under that name, without an extra nested folder. `--original-root` selects the archived name and is accepted only by full unpack. Single-file capsules keep their actual filename. With no `-o`, output goes beside the capsule. Derived folder names must pass portable-name checks, and output cannot replace the input capsule. Optional state records the published root name and retains project-relative executable intent. Compare ignores an outer project folder rename; repack records the current folder name. Selective extraction and explicit evidence recovery retain their existing path layouts.

`recover` is an explicit salvage operation, retaining separate evidence in addition to ordinary basic `u`/`v`. It requires `-o` naming a new directory, and rejects overwrite/backup, selection, compression, archive-profile and export-limit options. It accepts timestamp flags and `-q`, but always prints a recovery warning. Exit 0 means recovery succeeded, not that the input was a valid CPC. Exit 2 means recovery failed. All archived user paths are retained under `files/`; original `.cpc` entries are isolated under `metadata/.cpc/`. `recovery.json` records the first metadata failure and limitations. Newly generated `.files.cpc-state` supports `cpc r <destination>/files -o <new-capsule>` with archive profile and TAR executable intent. Ordinary packing exclusions, including `.cpcignore`, still apply. The source archive is never a default repack destination.

If original CPC metadata is invalid, recovery uses the TAR dates by default and never inherits its root, source, profile, or executable-state declarations. Invalid or unsupported TAR dates require explicit `--normalize-times`. Fully valid metadata retains its timestamp policy; `--preserve-times` cannot recover dates from a known normalized capsule. No missing file, directory date, or original permission policy is invented.

The timestamp flags are mutually exclusive. They apply to pack, unpack, repack, selective extract, root rename, and source export. Verification/list/inspect/compare/join reject these flags; exporting an existing capsule also rejects them because it preserves exact bytes. Restore uses verified capsule policy, or TAR dates when metadata is unverified. Only `--state` saves a sidecar; repack and restored-source export inherit it when present and default to preservation otherwise. Legacy capsules/sidecars without the policy remain normalized. Asking restore to preserve dates from a normalized capsule fails with `TIMESTAMPS_UNAVAILABLE`. An explicit normalization override can recover a preserved capsule on a filesystem that cannot apply its dates, and records the changed policy only when `--state` is requested.

Export writes one ordinary capsule when it fits; otherwise it publishes a complete paired set in a new directory. A source folder's export destination must be outside that source. Source packing honors selection/compression flags; an existing capsule is preserved without repacking. Export and join require `-o` and reject `-f`/`-b`. Join accepts either one directory (only its immediate `.cpcpart.md` files) or an explicit complete list of parts in any order. It produces a verified ordinary capsule, not an extracted workspace. A part passed to ordinary pack/unpack fails with guidance to join first. The minimum export limit is 1 KiB; multipart exports must also accommodate the self-contained `HANDOFF.md` receiver/instructions, or fail with `HANDOFF_LIMIT` and the required byte count. At most 1,000 parts are supported.
