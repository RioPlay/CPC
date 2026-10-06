# CPC CLI Profile

The CLI is not part of the CPC wire grammar, but this profile standardizes the intended user experience.

## Minimal interactive surface

```text
cpc
cpc <thing>
cpc p <thing>
cpc u <capsule>
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
-a       archive profile
-m       maximum compression effort
--preset N  XZ preset 0-9 (default 6; mutually exclusive with -m)
--normalize-times  discard original modification dates for compact/reproducible output
--preserve-times   preserve modification dates (new-pack default; repack inherits saved policy)
--report    selected bytes, output size, and largest included files
--max-file-size SIZE  export only, default 25MB (decimal); MiB also accepted
```

Outer filesystem copy/move/rename operations are intentionally not duplicated by CPC.

The timestamp flags are mutually exclusive. They apply to pack, unpack, repack, selective extract, root rename, and source export. Verification/list/inspect/compare/join reject these flags; exporting an existing capsule also rejects them because it preserves exact bytes. Restore inherits the capsule policy and writes it to the adjacent sidecar; repack and restored-source export inherit the sidecar policy. Legacy capsules/sidecars without the policy remain normalized. Asking restore to preserve dates from a normalized capsule fails with `TIMESTAMPS_UNAVAILABLE`. An explicit normalization override can recover a preserved capsule on a filesystem that cannot apply its dates, and records the changed policy.

Export writes one ordinary capsule when it fits; otherwise it publishes a complete paired set in a new directory. A source folder's export destination must be outside that source. Source packing honors selection/compression flags; an existing capsule is preserved without repacking. Export and join require `-o` and reject `-f`/`-b`. Join accepts either one directory (only its immediate `.cpcpart.md` files) or an explicit complete list of parts in any order. It produces a verified ordinary capsule, not an extracted workspace. A part passed to ordinary pack/unpack fails with guidance to join first. The minimum export limit is 1 KiB; multipart exports must also accommodate the self-contained `HANDOFF.md` receiver/instructions, or fail with `HANDOFF_LIMIT` and the required byte count. At most 1,000 parts are supported.
