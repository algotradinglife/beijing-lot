# Adhoc publication attestation

Operational adhoc packages require an Ed25519 publication attestation. Package
hashes prove content integrity; the attestation proves that the dedicated
Decision API publication authority approved that exact content.

`config/adhoc_publication_keys.json` is the version-controlled public-key
registry. It contains only public keys, key identifiers and lifecycle state.
An active production key must be added through reviewed configuration change.
Test keys are created by fixtures and must never be added to this registry.

The private key is an unencrypted PKCS#8 PEM secret mounted read-only for a
dedicated Decision API operating-system identity. It must not be committed,
logged, returned by an API, written into a manifest, or inherited by
adhoc/manual workers. Configure the service with:

- `BEIDAN_ADHOC_PUBLICATION_PRIVATE_KEY_FILE`: absolute path to the mounted PEM.
- `BEIDAN_ADHOC_PUBLICATION_KEY_ID`: reviewed `key_id` in the pinned registry.

Generate the key outside the repository on the deployment host or secret
provisioner. The following example emits the private key only to the explicitly
selected secret path and prints the registry-safe raw public key:

```bash
install -d -m 0700 /run/secrets/beidan-decision-api
openssl genpkey -algorithm ED25519 \
  -out /run/secrets/beidan-decision-api/adhoc-publication.pem
chmod 0400 /run/secrets/beidan-decision-api/adhoc-publication.pem
uv run python - /run/secrets/beidan-decision-api/adhoc-publication.pem <<'PY'
import base64
import sys
from pathlib import Path
from cryptography.hazmat.primitives import serialization

private_key = serialization.load_pem_private_key(
    Path(sys.argv[1]).read_bytes(), password=None
)
public_key = private_key.public_key().public_bytes(
    serialization.Encoding.Raw,
    serialization.PublicFormat.Raw,
)
print(base64.b64encode(public_key).decode("ascii"))
PY
```

Set ownership of the PEM to the dedicated API service user before startup. The
API user must be the only runtime identity able to read the PEM and write the
operational package root. Scrapers, adhoc/manual jobs, research workers and
interactive shells run under different identities, receive neither publication
environment variable, and have no secret mount or operational-root write
permission. Container deployments enforce the same boundary with a
service-specific read-only secret mount and a separate writable package volume.

If the private key path or key identifier is absent, or the key file is
unreadable, the Decision API returns HTTP 503 with the structured error
`PUBLICATION_AUTHORITY_UNAVAILABLE` before operational generation. A direct
library caller without a key may produce an `UNATTESTED_AUDIT_ONLY` record in
its own audit root, but it cannot download it as current. Unknown, retired or
revoked registry keys and invalid signatures also fail closed without an
operational fallback.

Key rotation procedure:

1. Generate a new key and add only its public key with a new `key_id`, matching
   `usage`, and `active` status in a reviewed registry update.
2. Deploy that registry before switching signers.
3. Mount the new private key only to the API identity, update both environment
   variables atomically, and restart the service.
4. Generate a canary package and independently verify its key identifier,
   signature, formal-selection binding and operational download boundary.
5. Mark the old key `retired` in a second reviewed change after the cutover.
   Use `revoked` for an emergency disablement. Packages signed by any non-active
   key fail closed and must not be served as current.
6. Remove the retired private key from the service secret mount after rollback
   is no longer permitted; retain only the reviewed public lifecycle record.

No Python naming convention substitutes for process/identity isolation: code
running inside the API authority process is an API compromise. Manual/runtime
workers must run without the private-key mount and without write access to the
operational package root.
