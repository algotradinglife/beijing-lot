# Adhoc publication attestation

Operational adhoc packages require an Ed25519 publication attestation. Package
hashes prove content integrity; the attestation proves that the dedicated
Decision API publication authority approved that exact content.

`config/adhoc_publication_keys.json` is the version-controlled public-key
registry. It contains only public keys, key identifiers and lifecycle state.
An active production key must be added through reviewed configuration change.
Test keys are created by fixtures and must never be added to this registry.

The private key is a PEM secret mounted read-only for the Decision API service
identity. It must not be committed, logged, returned by an API, written into a
manifest, or inherited by adhoc/manual workers. The service process reads the
private-key path and key identifier from its deployment secret configuration.

If the private key is missing, unreadable, malformed, unknown, retired or
revoked, operational publication fails closed with
`PUBLICATION_AUTHORITY_UNAVAILABLE`. A generated package may remain an
`UNATTESTED_AUDIT_ONLY` record, but it cannot be downloaded as current.

Key rotation procedure:

1. Add the new public key with a new `key_id` and `active` status in a reviewed
   registry update.
2. Mount its private key only to the API service identity and switch the API to
   its key identifier.
3. Verify a newly generated package against the pinned registry.
4. Mark the old key `retired`; use `revoked` for emergency disablement.

No Python naming convention substitutes for process/identity isolation: code
running inside the API authority process is an API compromise. Manual/runtime
workers must run without the private-key mount and without write access to the
operational package root.
