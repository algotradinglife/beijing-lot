# Issue #229 candidate-mode evidence debt

Audit mode: `candidate`.

The PI takeover closes every conclusion-affecting R3 defect before #229 may
leave `Blocked`. The following evidence-hardening items do not change the
observed zero causal divergence support or the `BLOCKED_DATA_DEFECT`
disposition and are carried to the unified-model `finalize` gate:

| debt | scope | conclusion impact | finalize closure |
|---|---|---|---|
| E1 | Git commit binding | None. A commit cannot embed its own SHA. The package binds code, notebook, dependency and source hashes; the independent EV receipt binds the exact audited PR HEAD. | Replace symbolic package wording with an external 40-hex `AUDITED_SHA` receipt contract and reject absent/mismatched external binding. |
| E2 | Full handoff schema normalization | None for the zero-support census. Key/domain coverage is incomplete on some aggregate/empty profile tables. | Add physical row identities or explicit aggregate-key semantics and validate every declared domain/cardinality. |
| E3 | Crash-restart journal | None for scientific values. In-process atomic swap is tested, but `target + previous` after process death remains ambiguous without a durable phase journal. | Add a same-directory durable transaction journal and kill/restart probes before production data publication. |

No debt permits #209 to treat the current package as divergence-model ready.

