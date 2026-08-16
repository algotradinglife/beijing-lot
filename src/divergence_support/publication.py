"""Issue #232 — atomic writers (reuse #229 crash-durable publication)."""

from __future__ import annotations


from divergence_profile import publication as _publication

# Re-export the verified #229 atomic writers so #232 artifacts get the same
# crash-durable semantics (temp + fsync + rename + parent fsync).
fsync_file = _publication.fsync_file
fsync_dir = _publication.fsync_dir
atomic_write_bytes = _publication.atomic_write_bytes
atomic_write_text = _publication.atomic_write_text
atomic_write_json = _publication.atomic_write_json
atomic_write_csv = _publication.atomic_write_csv
atomic_write_parquet = _publication.atomic_write_parquet
atomic_save_figure = _publication.atomic_save_figure
atomic_publish_directory = _publication.atomic_publish_directory
fsync_tree = _publication.fsync_tree

__all__ = [
    "fsync_file",
    "fsync_dir",
    "atomic_write_bytes",
    "atomic_write_text",
    "atomic_write_json",
    "atomic_write_csv",
    "atomic_write_parquet",
    "atomic_save_figure",
    "atomic_publish_directory",
    "fsync_tree",
]
