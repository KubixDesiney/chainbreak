# CHAINBREAK Lab Log

The human-readable counterpart to the evidence bundles. Every experiment block appends an
entry. Exclusions are recorded **with reasons** — that is the single most important honesty
mechanism in the protocol, and a suite whose exclusions are undocumented is not publishable.

Format per [EXPERIMENT_PROTOCOL §8](../../EXPERIMENT_PROTOCOL.md#8-lab-log).

---

## No experiments have been run

As of the current commit, CHAINBREAK's architecture and specifications are complete and the
domain model, capability catalog and scenario corpus are implemented and verified. **No
scenario has been executed against AWS, and no measurement exists.**

The first entry in this file will be written during milestone M17.

---

## Template

```
## YYYY-MM-DD block-NN
checklist:            0.1-0.9 pass | note any that failed and what was done
infrastructure:       applied HH:MM UTC, fingerprint sha256:…, negative controls enabled
adapter/catalog:      adapter 0.1.0, catalog 1.0.0, chainbreak 0.1.0, commit abc1234 (clean)
scenarios:            <path> v<version>, …
runs:                 <run-id>, …
negative controls:    nc-… -> DETECTOR_OK | DETECTOR_FAILURE
exclusions:           run <id> trial <n> excluded, reason …
observation:          <measured value with n, interval, mechanism, region>
anomalies:            …
notes:                block window; next block scheduled (control C-7 requires >= 3 blocks)
```

## Rules

- One entry per block, written at the time, not reconstructed afterwards.
- Record the checklist result even when everything passed.
- Record every exclusion, with its reason and the run ID.
- A block containing a `DETECTOR_FAILURE` is unvalidated. Record it, and do not publish any
  result from it.
- State observations in measurement language: "authorization remained effective for X–Y s
  after the mutation request, mechanism M, n=k". Not "revocation is slow".
