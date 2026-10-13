# CPC format reference

The canonical CPC wire format is version **1**. The specification is **0.3-draft**, accompanying reference tooling **0.3.0-rc.7**. Basic readers can restore a valid marker-delimited payload despite header/hash problems, with integrity warnings; strict readers and reference writers require canonical output.

| Document | Purpose |
|---|---|
| [Specification](SPEC.md) | Wire grammar, archive structure, and lifecycle semantics |
| [Conformance](CONFORMANCE.md) | Reader, writer, and lifecycle requirements |
| [CLI profile](CLI_PROFILE.md) | Commands and flags |
| [Security model](SECURITY.md) | Threat model and extraction requirements |
| [Test vector](TEST_VECTOR.md) | Expected bytes and hashes for the [fixture](test-vector.cpc.md) |

Machine-readable version and fixture metadata are in [STANDARD.json](STANDARD.json).
