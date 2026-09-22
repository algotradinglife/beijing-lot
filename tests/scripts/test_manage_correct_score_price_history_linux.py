"""Contract examples for the collector's Linux environment. No network, no browser launched.

The collector used to be pointed at a WSL setup through /mnt/c paths: Chrome was the Windows
build and both profiles lived under the Windows user directory. This host is the machine the
project runs on and it is native Ubuntu, so those defaults described a machine that no longer
exists. These examples pin the Linux defaults and the command line the fetcher builds from them.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.manage_correct_score_price_history import (  # noqa: E402
    DEFAULT_AUTH_PROFILE,
    DEFAULT_CHROME,
    DEFAULT_NOWSCORE_PROFILE,
    DEFAULT_PROFILE_ROOT,
    ChromeDumpFetcher,
    chrome_path_argument,
)


def test_the_import_carries_no_side_effects() -> None:
    """Importing the collector must not fetch, launch a browser, or touch the store."""
    assert DEFAULT_CHROME.is_absolute()
    assert not DEFAULT_CHROME.exists() or DEFAULT_CHROME.is_file()


def test_the_defaults_describe_this_host_not_wsl() -> None:
    """The Windows paths belonged to the setup the project migrated away from."""
    for path in (DEFAULT_CHROME, DEFAULT_AUTH_PROFILE, DEFAULT_NOWSCORE_PROFILE, DEFAULT_PROFILE_ROOT):
        assert "/mnt/c" not in str(path), path
        assert not str(path).startswith("/mnt/"), path
    assert DEFAULT_CHROME == Path("/usr/bin/google-chrome-stable")
    assert DEFAULT_PROFILE_ROOT == Path.home() / ".local/share/beijing-lot"
    assert DEFAULT_AUTH_PROFILE.parent == DEFAULT_PROFILE_ROOT
    assert DEFAULT_NOWSCORE_PROFILE.parent == DEFAULT_PROFILE_ROOT


def test_the_two_profiles_are_distinct_directories() -> None:
    """Okooo and Nowscore are collected under separate sessions and must not share a profile."""
    assert DEFAULT_AUTH_PROFILE != DEFAULT_NOWSCORE_PROFILE


def test_chrome_path_argument_resolves_without_wsl_translation() -> None:
    """No wslpath: the path is used as the Linux path it already is."""
    assert chrome_path_argument(Path("~/somewhere")) == str(Path.home() / "somewhere")


def test_the_fetcher_builds_a_linux_command_line(tmp_path: Path) -> None:
    """The command the fetcher would run carries the Linux profile and no Windows argument."""
    executable = tmp_path / "chrome"
    executable.write_text("#!/bin/sh\necho '<html></html>'\n", encoding="utf-8")
    executable.chmod(0o755)
    profile = tmp_path / "profile"
    fetcher = ChromeDumpFetcher(executable, profile, "Default")
    assert fetcher.profile_argument == str(profile.resolve())
    assert "/mnt/" not in fetcher.profile_argument
    assert profile.is_dir()  # created so Chrome has somewhere to write


def test_a_missing_executable_is_refused(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        ChromeDumpFetcher(tmp_path / "nope", tmp_path / "profile", "Default")
