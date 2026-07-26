"""Read-only provenance audit for historical correct-score price vectors."""

from .audit import (
    AUDIT_ID,
    ScorePriceAuditError,
    audit_inputs,
    parse_input_spec,
    verify_audit_package,
    write_audit_artifacts,
)

__all__ = [
    "AUDIT_ID",
    "ScorePriceAuditError",
    "audit_inputs",
    "parse_input_spec",
    "verify_audit_package",
    "write_audit_artifacts",
]
