"""Immutable verifier anchor for the committed #318 artifact package."""

# Set after deterministic replay.  A verifier never trusts a package-supplied
# manifest as its own root of trust.
EXPECTED_MANIFEST_SHA256 = "261c7dcaaf731affed2ff2eb26ccec8dbc0127787cb8b4fe65f61e6c2e0006a2"
