"""Notification helpers for auto-mode (iMessage + macOS notification fallback).

iMessage is delivered via AppleScript to Messages.app. Requires the user's
Apple ID to be signed in to Messages on this Mac. If Messages.app isn't
logged in (no iMessage service), we fall back to a system notification and
log a warning.
"""
from __future__ import annotations

import logging
import shlex
import subprocess
from typing import Tuple

log = logging.getLogger(__name__)

DEFAULT_PHONE = "+861234567890"


def messages_app_logged_in() -> Tuple[bool, str]:
    """Lightweight probe: count Messages accounts. Many other AppleScript
    queries against Messages return -10000 even when sending works fine,
    so we use the simplest possible query.
    """
    try:
        out = subprocess.run(
            ["osascript", "-e",
             'tell application "Messages" to count of accounts'],
            capture_output=True, text=True, timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return False, f"osascript unavailable: {e}"
    if out.returncode != 0:
        return False, f"osascript error: {out.stderr.strip()}"
    n = out.stdout.strip()
    if not n or n == "0":
        return False, "no Messages accounts configured"
    return True, f"{n} account(s)"


def send_imessage(phone: str, body: str) -> Tuple[bool, str]:
    """Send an iMessage via AppleScript. Returns (ok, detail)."""
    safe_body = body.replace("\\", "\\\\").replace('"', '\\"')
    safe_phone = phone.replace('"', '')
    script = (
        f'tell application "Messages"\n'
        f'  set targetService to 1st service whose service type = iMessage\n'
        f'  set targetBuddy to buddy "{safe_phone}" of targetService\n'
        f'  send "{safe_body}" to targetBuddy\n'
        f'end tell'
    )
    try:
        out = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=15,
        )
    except subprocess.TimeoutExpired as e:
        return False, f"timeout: {e}"
    except (FileNotFoundError, OSError) as e:
        # Non-macOS host (e.g. WSL/Linux): osascript absent. Degrade to no-op.
        log.warning("iMessage unavailable on this platform: %s", e)
        return False, f"osascript unavailable: {e}"
    if out.returncode != 0:
        err = out.stderr.strip()
        log.error("iMessage send failed: %s", err)
        post_notification("北单自动模式", f"iMessage 发送失败: {err[:80]}")
        return False, err
    return True, "sent"


def post_notification(title: str, body: str) -> None:
    """macOS notification fallback. Best-effort."""
    safe_title = title.replace('"', '')
    safe_body = body.replace('"', '')
    script = f'display notification "{safe_body}" with title "{safe_title}"'
    try:
        subprocess.run(["osascript", "-e", script],
                       capture_output=True, timeout=5)
    except Exception as e:
        log.warning("notification failed: %s", e)


def notify(phone: str, title: str, body: str) -> Tuple[bool, str]:
    """Send via iMessage; on failure, also post a macOS notification.

    The full message text combines title + body for iMessage.
    """
    full = f"[{title}] {body}"
    ok, detail = send_imessage(phone, full)
    if not ok:
        post_notification(title, body)
    return ok, detail
