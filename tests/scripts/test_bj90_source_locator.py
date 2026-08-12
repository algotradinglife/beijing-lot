"""Focused source-resolution coverage for #90's executable archived runners."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from bj90_source_locator import RELATIVE_SOURCE, resolve_source  # noqa: E402


def touch_source(root: Path) -> Path:
    source = root / RELATIVE_SOURCE
    source.parent.mkdir(parents=True)
    source.touch()
    return source


def test_normal_checkout_prefers_repository_relative_source(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    source = touch_source(checkout)
    assert resolve_source(checkout) == source.resolve()


def test_isolated_checkout_accepts_explicit_external_source_without_copying(tmp_path: Path) -> None:
    isolated_checkout = tmp_path / "isolated-checkout"
    isolated_checkout.mkdir()
    external_source = touch_source(tmp_path / "canonical-input-store")
    assert not (isolated_checkout / RELATIVE_SOURCE).exists()
    assert resolve_source(isolated_checkout, external_source) == external_source.resolve()


def test_nested_worktree_fallback_is_documented_and_deterministic(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    nested_worktree = repository / ".worktrees" / "strategy"
    nested_worktree.mkdir(parents=True)
    source = touch_source(repository)
    assert resolve_source(nested_worktree) == source.resolve()


def test_missing_source_lists_attempted_paths(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="attempted"):
        resolve_source(tmp_path / "normal-checkout")
