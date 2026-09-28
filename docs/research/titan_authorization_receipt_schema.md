# Titan automation authorization receipt

The clean collector is deliberately fail-closed for operational collection.
A human must obtain written permission covering both Titan origins and save a
non-secret receipt outside the data root. Do not create this record from robots
text, a successful probe, or an inference about public availability.

```json
{
  "schema_version": "titan_collection_authorization_v1",
  "source_id": "titan",
  "automation_permitted": true,
  "authorization_basis": "<written permission or contract reference>",
  "evidence_uri": "<durable internal or provider evidence URI>",
  "allowed_origins": [
    "data.titan007.com",
    "1x2d.titan007.com"
  ]
}
```

The file must contain no API token, cookie, password or personally sensitive
content. The collector stores only its SHA-256 with the roster capture; the
hash becomes part of each sealed release manifest. `--probe` remains a
single-fixture capability check and is never operational authorization.

Before an operator begins unattended collection, the PI must verify the
provider's scope, rate limits, permitted endpoints, retention terms and expiry
or revocation conditions. No actual Titan authorization receipt is currently
present in this repository.
