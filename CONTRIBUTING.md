# Contributing to CPC

CPC is still in Release Candidate development.

## Priorities

Changes should improve at least one of:

- transfer density;
- deterministic recovery;
- cross-platform portability;
- safety;
- LLM interoperability;
- implementation simplicity.

Avoid increasing the receiving-side dependency or parser surface without measurable benefit.

## Before proposing a wire-format change

A change to the CPC header, Base64 transport, XZ layer, TAR representation, or reconstruction semantics requires:

1. a demonstrated compatibility or efficiency problem;
2. a test fixture reproducing it;
3. an interoperability impact assessment;
4. an update to the CPC specification and conformance tests.

CPC format changes should be evidence-driven rather than cosmetic.

## Testing

Run the regression suite before submitting changes:

```bash
python tests/test_cpc.py
```

Cross-platform and LLM-interoperability results are especially valuable.


## Contribution policy

CPC does not currently accept external code contributions.

You are welcome to submit:
- bug reports;
- interoperability results;
- benchmark data;
- security reports;
- test cases;
- feature suggestions.

Code changes to the official CPC repository are maintained by RioPlay.

Forks are permitted under the MIT License.
