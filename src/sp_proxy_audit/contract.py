"""Immutable verifier anchor for the committed #318 artifact package."""

# Set after deterministic replay.  A verifier never trusts a package-supplied
# manifest as its own root of trust.
EXPECTED_MANIFEST_SHA256 = (
    "144096904442a57d506faa986887ea628d051c6952b3af1d3c71cf8b8509a15b"
)
