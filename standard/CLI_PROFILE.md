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
--preset N  XZ preset 0-9 (default 9; mutually exclusive with -m)
--report    selected bytes, output size, and largest included files
```

Outer filesystem copy/move/rename operations are intentionally not duplicated by CPC.
