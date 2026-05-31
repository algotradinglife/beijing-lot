"""Extract logged-in 500.com session cookies from Chrome and save to data/.

Run this script whenever the live collector reports that vol_pct is blank
(session expired). Requires Chrome Profile 1 to have an active 500.com login.

Usage:
    python scripts/refresh_500_cookies.py
    python scripts/refresh_500_cookies.py --verify   # also fetch page and check vol_pct
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict

ROOT = Path(__file__).resolve().parents[1]
COOKIE_FILE = ROOT / "data" / "500com_cookies.json"
CHROME_PROFILE = os.path.expanduser(
    "~/Library/Application Support/Google/Chrome/Profile 1/Cookies"
)
AUTH_COOKIE_NAMES = (
    "ck", "ck_user", "ck_user2", "key", "token", "token_user",
    "sdc_session", "usercheck", "isautologin", "swid",
    "CLICKSTRN_ID", "coop_type", "HMACCOUNT", "motion_id",
)

try:
    from Crypto.Cipher import AES
except ImportError:
    print("pycryptodome required: pip install pycryptodome")
    sys.exit(1)


def _get_chrome_key() -> bytes:
    pw = subprocess.run(
        ["security", "find-generic-password", "-w", "-s", "Chrome Safe Storage"],
        capture_output=True, text=True,
    ).stdout.strip()
    if not pw:
        raise RuntimeError("Could not read Chrome Safe Storage key from macOS Keychain")
    return hashlib.pbkdf2_hmac("sha1", pw.encode(), b"saltysalt", 1003, dklen=16)


def _decrypt(enc: bytes, key: bytes) -> str:
    """Decrypt a Chrome cookie value (macOS v10 format).

    Format: b'v10' + 16-byte IV + AES-128-CBC ciphertext.
    First decrypted block (16 bytes) is metadata; skip it.
    """
    if not enc or enc[:3] != b"v10":
        return enc.decode("utf-8", errors="replace") if isinstance(enc, bytes) else str(enc)
    iv = enc[3:19]
    ciphertext = enc[19:]
    decrypted = AES.new(key, AES.MODE_CBC, IV=iv).decrypt(ciphertext)
    payload = decrypted[16:]  # skip metadata block
    pad = payload[-1]
    if 1 <= pad <= 16:
        payload = payload[:-pad]
    return payload.decode("utf-8", errors="replace")


def extract_cookies(profile_path: str = CHROME_PROFILE) -> Dict[str, str]:
    if not os.path.exists(profile_path):
        raise FileNotFoundError(f"Chrome cookie DB not found: {profile_path}")
    key = _get_chrome_key()
    tmp = tempfile.mktemp(suffix=".sqlite")
    try:
        shutil.copy2(profile_path, tmp)
        conn = sqlite3.connect(tmp)
        rows = conn.execute(
            "SELECT name, encrypted_value FROM cookies "
            "WHERE host_key LIKE '%.500.com%'"
        ).fetchall()
        conn.close()
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass

    return {name: _decrypt(enc, key) for name, enc in rows}


def save_cookies(cookies: Dict[str, str]) -> None:
    COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
    auth = {k: cookies[k] for k in AUTH_COOKIE_NAMES if k in cookies}
    COOKIE_FILE.write_text(json.dumps(auth, indent=2, ensure_ascii=False))
    print(f"Saved {len(auth)} auth cookies → {COOKIE_FILE}")
    for k, v in auth.items():
        print(f"  {k}={v[:50]!r}")


def load_cookies(path: Path = COOKIE_FILE) -> Dict[str, str]:
    """Load saved cookies from file. Returns empty dict if file missing."""
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def verify(cookies: Dict[str, str]) -> bool:
    """Fetch the bjdc page with auth cookies and check vol_pct population."""
    import re
    import requests as req

    cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
    UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    r = req.get("https://trade.500.com/bjdc/",
                headers={"User-Agent": UA, "Cookie": cookie_header}, timeout=15)

    logged_in = "退出" in r.text
    tzbl = re.findall(r'class="[^"]*tzbl[^"]*"[^>]*>([^<]+)<', r.text)
    non_blank = [v for v in tzbl if v.strip() not in ("--", "")]

    print(f"\nVerification: status={r.status_code}, logged_in={logged_in}")
    print(f"  tzbl spans: {len(tzbl)}, non-blank: {len(non_blank)}")

    if non_blank:
        print(f"  ✓ vol_pct live: {non_blank[:6]}")
        return True
    elif logged_in:
        print("  ✓ Authenticated. vol_pct shows '--' — no active betting window right now.")
        print("    (vol_pct only appears during live betting; try again during next issue.)")
        return True
    else:
        print("  ✗ Not authenticated — cookies may be expired. Re-login to 500.com and retry.")
        return False


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true",
                    help="Fetch 500.com page and confirm vol_pct appears")
    ap.add_argument("--profile", default=CHROME_PROFILE,
                    help="Path to Chrome Cookies SQLite DB")
    args = ap.parse_args()

    print("Extracting 500.com cookies from Chrome Profile 1...")
    cookies = extract_cookies(args.profile)
    save_cookies(cookies)

    if args.verify:
        ok = verify({k: cookies[k] for k in AUTH_COOKIE_NAMES if k in cookies})
        sys.exit(0 if ok else 1)
