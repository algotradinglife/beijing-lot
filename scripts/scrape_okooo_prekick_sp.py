#!/usr/bin/env python3
"""Repair of the legacy VBA `下载sp()`: capture and freeze Okooo 10h SP rows."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.okooo_prekick_sp import (  # noqa: E402
    DEFAULT_ROOT,
    MARKET_PATHS,
    OkoooParseError,
    history_url,
    issue_url,
    outcome_values,
    parse_history_page,
    parse_issue_page,
    publish_bundle,
    select_asof_10h,
    verify_bundle,
)


DEFAULT_CHROME = Path("/mnt/c/Program Files/Google/Chrome/Application/chrome.exe")
DEFAULT_AUTH_PROFILE = Path("/mnt/c/Users/hhusl/AppData/Local/OkoooCollectorProfile")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    capture = sub.add_parser("capture")
    capture.add_argument("--issue", required=True)
    capture.add_argument("--markets", nargs="+", choices=tuple(MARKET_PATHS), default=("correct_score", "half_full"))
    capture.add_argument("--provider-code", default="14")
    capture.add_argument("--chrome", type=Path, default=DEFAULT_CHROME)
    capture.add_argument("--chrome-user-data-dir", type=Path)
    capture.add_argument("--profile-directory", default="Default")
    capture.add_argument("--output-root", type=Path, default=DEFAULT_ROOT)
    capture.add_argument("--match-limit", type=int)
    capture.add_argument("--delay", type=float, default=2.0)
    capture.add_argument("--allow-partial", action="store_true")
    login = sub.add_parser("login")
    login.add_argument("--chrome", type=Path, default=DEFAULT_CHROME)
    login.add_argument("--chrome-user-data-dir", type=Path, default=DEFAULT_AUTH_PROFILE)
    login.add_argument("--profile-directory", default="Default")
    verify = sub.add_parser("verify")
    verify.add_argument("bundle", type=Path)
    inspect_issue = sub.add_parser("inspect-issue")
    inspect_issue.add_argument("html", type=Path)
    inspect_issue.add_argument("--issue", required=True)
    inspect_history = sub.add_parser("inspect-history")
    inspect_history.add_argument("html", type=Path)
    inspect_history.add_argument("--source-url", default="")
    return parser.parse_args()


def chrome_path_argument(path: Path, windows_chrome: bool) -> str:
    resolved = path.expanduser().resolve()
    if not windows_chrome:
        return str(resolved)
    converted = subprocess.run(
        ["wslpath", "-w", str(resolved)],
        capture_output=True,
        text=True,
        timeout=5,
        check=True,
    )
    return converted.stdout.strip()


class ChromeDumpFetcher:
    def __init__(
        self,
        executable: Path,
        *,
        user_data_dir: Path | None = None,
        profile_directory: str = "Default",
    ) -> None:
        self.executable = executable.expanduser().resolve()
        if not self.executable.is_file():
            raise FileNotFoundError(f"Chrome executable missing: {self.executable}")
        self.windows_chrome = str(self.executable).startswith("/mnt/")
        self.profile_directory = profile_directory
        self.persistent_profile = user_data_dir is not None
        windows_temp = Path("/mnt/c/Temp")
        if user_data_dir is not None:
            user_data_dir.expanduser().mkdir(parents=True, exist_ok=True)
            self.profile = None
            self.profile_argument = chrome_path_argument(user_data_dir, self.windows_chrome)
        else:
            profile_parent = windows_temp if self.windows_chrome and windows_temp.is_dir() else None
            self.profile = tempfile.TemporaryDirectory(prefix="okooo-chrome-", dir=profile_parent)
            self.profile_argument = chrome_path_argument(Path(self.profile.name), self.windows_chrome)

    def close(self) -> None:
        if self.profile is not None:
            self.profile.cleanup()

    def fetch(self, url: str) -> bytes:
        command = [
            str(self.executable),
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            "--disable-background-networking",
            f"--user-data-dir={self.profile_argument}",
            f"--profile-directory={self.profile_directory}",
            "--dump-dom",
            url,
        ]
        completed = subprocess.run(command, capture_output=True, timeout=45, check=False)
        if completed.returncode != 0 or not completed.stdout.strip():
            error = completed.stderr.decode("utf-8", errors="replace")[-1000:]
            raise RuntimeError(f"Chrome dump failed rc={completed.returncode}: {error}")
        return completed.stdout


def flattened_rows(match, market: str, source_url: str, rows, selected_only: bool = False):
    chosen = select_asof_10h(rows)
    source_rows = [chosen] if selected_only else rows
    output = []
    for row in source_rows:
        for value in outcome_values(row):
            output.append(
                {
                    "issue": match.issue,
                    "match_idx": match.match_idx,
                    "match_id": match.match_id,
                    "market": market,
                    "source_url": source_url,
                    "row_order": row.row_order,
                    "relative_label": row.relative_label,
                    "minutes_before_kickoff": row.minutes_before_kickoff,
                    **value,
                }
            )
    return output


def capture(arguments: argparse.Namespace) -> dict:
    fetcher = ChromeDumpFetcher(
        arguments.chrome,
        user_data_dir=arguments.chrome_user_data_dir,
        profile_directory=arguments.profile_directory,
    )
    raw_pages: dict[str, bytes] = {}
    history_rows: list[dict] = []
    selected_rows: list[dict] = []
    failures: list[dict] = []
    fetched_at = datetime.now(timezone.utc).isoformat()
    try:
        list_url = issue_url(arguments.issue)
        issue_payload = fetcher.fetch(list_url)
        raw_pages["issue.html"] = issue_payload
        try:
            matches = parse_issue_page(issue_payload, arguments.issue)
        except Exception as exc:
            if not arguments.allow_partial:
                raise
            failures.append(
                {
                    "issue": arguments.issue,
                    "match_idx": "",
                    "match_id": "",
                    "market": "issue_list",
                    "source_url": list_url,
                    "reason": f"{type(exc).__name__}: {exc}",
                }
            )
            matches = []
        if arguments.match_limit is not None:
            matches = matches[: arguments.match_limit]
        for match in matches:
            for market in arguments.markets:
                url = history_url(match.match_id, market, arguments.provider_code)
                name = f"{match.match_idx:03d}_{match.match_id}_{market}.html"
                try:
                    payload = fetcher.fetch(url)
                    raw_pages[f"history/{name}"] = payload
                    rows = parse_history_page(payload, url)
                    history_rows.extend(flattened_rows(match, market, url, rows))
                    selected_rows.extend(flattened_rows(match, market, url, rows, selected_only=True))
                except Exception as exc:  # preserve every per-page failure in the audit bundle
                    failures.append(
                        {
                            "issue": match.issue,
                            "match_idx": match.match_idx,
                            "match_id": match.match_id,
                            "market": market,
                            "source_url": url,
                            "reason": f"{type(exc).__name__}: {exc}",
                        }
                    )
                    if not arguments.allow_partial:
                        raise
                if arguments.delay > 0:
                    time.sleep(arguments.delay)
        return publish_bundle(
            issue=arguments.issue,
            fetched_at_utc=fetched_at,
            raw_pages=raw_pages,
            matches=matches,
            history=history_rows,
            selected=selected_rows,
            failures=failures,
            output_root=arguments.output_root,
            provider_code=arguments.provider_code,
            authentication_mode="persistent_authenticated_profile" if arguments.chrome_user_data_dir else "anonymous_temporary_profile",
        )
    finally:
        fetcher.close()


def main() -> int:
    arguments = parse_args()
    if arguments.command == "login":
        executable = arguments.chrome.expanduser().resolve()
        if not executable.is_file():
            raise FileNotFoundError(f"Chrome executable missing: {executable}")
        windows_chrome = str(executable).startswith("/mnt/")
        arguments.chrome_user_data_dir.expanduser().mkdir(parents=True, exist_ok=True)
        profile = chrome_path_argument(arguments.chrome_user_data_dir, windows_chrome)
        subprocess.Popen(
            [
                str(executable),
                f"--user-data-dir={profile}",
                f"--profile-directory={arguments.profile_directory}",
                issue_url("26075"),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        result = {
            "status": "login_window_opened",
            "chrome_user_data_dir": str(arguments.chrome_user_data_dir.expanduser().resolve()),
            "instruction": "请在专用窗口登录澳客，登录完成后关闭该窗口，再运行 capture。",
        }
    elif arguments.command == "verify":
        result = verify_bundle(arguments.bundle)
    elif arguments.command == "inspect-issue":
        rows = parse_issue_page(arguments.html.read_bytes(), arguments.issue)
        result = {
            "status": "valid",
            "issue": arguments.issue,
            "match_rows": len(rows),
            "match_idx": [row.match_idx for row in rows],
        }
    elif arguments.command == "inspect-history":
        rows = parse_history_page(arguments.html.read_bytes(), arguments.source_url)
        selected = select_asof_10h(rows)
        result = {
            "status": "valid",
            "history_rows": len(rows),
            "selected_relative_label": selected.relative_label,
            "selected_minutes_before_kickoff": selected.minutes_before_kickoff,
            "selected_outcomes": outcome_values(selected),
        }
    else:
        try:
            result = capture(arguments)
        except OkoooParseError as exc:
            print(json.dumps({"status": "rejected", "reason": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
