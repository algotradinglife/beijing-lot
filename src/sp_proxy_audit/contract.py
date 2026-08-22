"""Immutable verifier anchor for the committed #318 artifact package."""

# Set after deterministic replay.  A verifier never trusts a package-supplied
# manifest as its own root of trust.
EXPECTED_MANIFEST_SHA256 = "ac150126896aeb137e5b68d5c405d3a876f2bbc38c6878ad8c571bb064a8433c"
