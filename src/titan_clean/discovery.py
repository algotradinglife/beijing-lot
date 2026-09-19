"""Titan-owned fixture discovery, without Nowscore inputs."""

from __future__ import annotations

import re
from dataclasses import dataclass

TITAN_SOURCE_ID = "titan"
SCHEDULE_URL = "https://data.titan007.com/soccer_scheduleid.js"
EURO_1X2_URL = "https://1x2d.titan007.com/{fixture_id}.js"
_SCHEDULE_RE = re.compile(r'\bvar\s+soccer_scheduleid\s*=\s*"([0-9,]+)"\s*;', re.ASCII)


class TitanDiscoveryError(ValueError):
    """Raised when the Titan schedule surface cannot be proven well-formed."""


@dataclass(frozen=True)
class Euro1x2Quote:
    company_source_id: str
    bookmaker_source_name: str
    record_source_id: str
    ordinal: int
    home_odds: float | None
    draw_odds: float | None
    away_odds: float | None
    market_time_source_raw: str | None
    home_kelly: float | None
    draw_kelly: float | None
    away_kelly: float | None


@dataclass(frozen=True)
class Roster:
    fixture_ids: tuple[str, ...]


@dataclass(frozen=True)
class FixtureIdentity:
    provider_fixture_id: str
    kickoff_source_raw: str | None
    home_team_source_id: str | None
    away_team_source_id: str | None
    competition_source_id: str | None


def _decode_payload(payload: bytes, *, fallback_encoding: str | None = "gb18030") -> str:
    """Decode a Titan 1x2d.js payload with a three-layer strategy.

    1. BOM detection (deterministic): UTF-16 LE/BE, UTF-8 BOM.
    2. Strict UTF-8, then the known source encoding (default GB18030 —
       the 500-page encoding; Titan payloads are UTF-8/UTF-16 so this is a
       deterministic last resort for CJK bytes).
    3. charset-normalizer detection only when both strict attempts fail
       (short CJK fragments are unreliable to auto-detect: GB18030 text is
       frequently mis-detected as big5/cp949, so the detector must never
       shadow the known source encodings).
    """
    if payload[:2] == b"\xff\xfe":
        return payload.decode("utf-16", errors="strict")
    if payload[:2] == b"\xfe\xff":
        return payload.decode("utf-16", errors="strict")
    if payload[:3] == b"\xef\xbb\xbf":
        return payload.decode("utf-8-sig", errors="strict")
    try:
        decoded_utf8 = payload.decode("utf-8", errors="strict")
        # UTF-16 LE 无 BOM 时，偶数字节常为 ASCII（含 NUL），恰好是合法 UTF-8；
        # 用 NUL 密度判断是否其实是 UTF-16 文本。
        if payload.count(b"\x00") > max(1, len(payload) // 8):
            return _decode_utf16_without_bom(payload, decoded_utf8)
        return decoded_utf8
    except UnicodeDecodeError:
        pass
    if fallback_encoding is not None:
        try:
            return payload.decode(fallback_encoding, errors="strict")
        except UnicodeDecodeError:
            pass
    try:
        import charset_normalizer
        match = charset_normalizer.from_bytes(payload).best()
        if match is not None and match.encoding is not None:
            try:
                decoded = match.output()
                if isinstance(decoded, bytes):
                    return decoded.decode("utf-8", errors="strict")
                return str(decoded)
            except (UnicodeDecodeError, ValueError):
                pass
    except ImportError:
        pass
    raise UnicodeDecodeError("payload", payload, 0, 1, "no decoder succeeded")


def _decode_utf16_without_bom(payload: bytes, utf8_guess: str) -> str:
    """Best-effort decode of a no-BOM UTF-16 payload.

    Both UTF-16-LE and UTF-16-BE are tried; the one whose decoded text has
    the highest printable/ASCII ratio wins.  ``utf8_guess`` is the (garbled)
    UTF-8 decoding, used only when neither UTF-16 direction improves on it.
    """
    candidates = []
    for enc in ("utf-16-le", "utf-16-be"):
        try:
            text = payload.decode(enc, errors="strict")
        except UnicodeDecodeError:
            continue
        printable = sum(1 for ch in text if ch.isprintable() or ch in "\r\n\t")
        ratio = printable / max(1, len(text))
        candidates.append((ratio, text))
    if not candidates:
        return utf8_guess
    candidates.sort(key=lambda pair: pair[0], reverse=True)
    best_ratio, best_text = candidates[0]
    utf8_ratio = sum(1 for ch in utf8_guess if ch.isprintable() or ch in "\r\n\t") / max(1, len(utf8_guess))
    if best_ratio > utf8_ratio:
        return best_text
    return utf8_guess


def _first(payload: str, pattern: str) -> str | None:
    match = re.search(pattern, payload, flags=re.ASCII)
    return match.group(1).strip() if match and match.group(1).strip() else None


def parse_fixture_identity(payload: bytes, *, provider_fixture_id: str) -> FixtureIdentity:
    """Extract only Titan-native fixture identity fields from one raw payload.

    Values retain their raw source form. Provider timestamps are not availability
    clocks and therefore deliberately remain unparsed here.
    """
    if not provider_fixture_id.isdecimal() or int(provider_fixture_id) <= 0:
        raise TitanDiscoveryError("fixture id must be a positive decimal string")
    text = _decode_payload(payload)
    # 现代格式: var game + var gameDetail；2010 早期格式: 裸 game=Array（无 gameDetail）。
    # 两者都含 game 数组，仅 var 前缀与 gameDetail 存在性不同。
    if not re.search(r"\b(?:var\s+)?game\s*=\s*Array\(", text, flags=re.ASCII):
        raise TitanDiscoveryError("Titan Euro fixture payload is missing history arrays")
    return FixtureIdentity(
        provider_fixture_id=provider_fixture_id,
        kickoff_source_raw=_first(text, r'MatchTime="([^"]+)"'),
        home_team_source_id=_first(text, r"hometeamID=([^;]+);"),
        away_team_source_id=_first(text, r"guestteamID=([^;]+);"),
        competition_source_id=_first(text, r"sclassId=([^;]+);"),
    )


def _array_items(text: str, variable: str, *, var_prefix: bool = True) -> tuple[str, ...]:
    """Extract a JS Array(...) literal's string items.

    2010 早期格式的 game 数组是裸 `game=Array(...)`（无 var 前缀），
    现代格式是 `var game=Array(...)`。var_prefix=False 接受两种写法。
    """
    prefix = r"\b(?:var\s+)?" if not var_prefix else r"\bvar\s+"
    match = re.search(rf"{prefix}{re.escape(variable)}\s*=\s*Array\((.*?)\)\s*;", text, flags=re.ASCII | re.DOTALL)
    if match is None:
        raise TitanDiscoveryError(f"Titan {variable} array is absent")
    return tuple(bytes(item, "utf-8").decode("unicode_escape") for item in re.findall(r'"((?:[^"\\\\]|\\\\.)*)"', match.group(1)))


def _positive_float(value: str | None) -> float | None:
    try:
        parsed = float(value) if value is not None else 0.0
    except ValueError:
        return None
    return parsed if parsed > 0 else None


def parse_euro_1x2_quotes(payload: bytes) -> tuple[Euro1x2Quote, ...]:
    """Normalize Titan 1X2 rows while retaining provider market time as source state.

    现代格式: `var game`（公司映射+开盘/即时快照）+ `var gameDetail`（完整变更历史）。
    2010 早期格式: 裸 `game=Array`（每公司单条 24 字段记录，含开盘 [3-5] 与
    即时 [10-12] 赔率及更新时间 [20]），无 gameDetail —— 该快照本身即该期
    数据的全部欧赔信息，开盘与即时各展开为一条 quote（ordinal 0/1）。
    """
    text = _decode_payload(payload)
    game_items = _array_items(text, "game", var_prefix=False)
    has_detail = re.search(r"\bvar\s+gameDetail\s*=\s*Array\(", text, flags=re.ASCII) is not None
    quotes: list[Euro1x2Quote] = []
    if not has_detail:
        # 2010 早期单快照：每条 game 项直接展开为开盘 + 即时两条 quote。
        for item in game_items:
            fields = item.split("|")
            if len(fields) < 21:
                continue
            record_id = fields[1]
            bookmaker = fields[2]
            company_id = fields[0]
            market_time = fields[20]
            home_init, draw_init, away_init = (_positive_float(fields[i]) for i in (3, 4, 5))
            home_cur, draw_cur, away_cur = (_positive_float(fields[i]) for i in (10, 11, 12))
            if home_init is None or draw_init is None or away_init is None:
                continue
            quotes.append(Euro1x2Quote(
                company_source_id=company_id, bookmaker_source_name=bookmaker,
                record_source_id=record_id, ordinal=0, home_odds=home_init,
                draw_odds=draw_init, away_odds=away_init, market_time_source_raw=market_time,
                home_kelly=None, draw_kelly=None, away_kelly=None,
            ))
            if home_cur is not None and draw_cur is not None and away_cur is not None:
                quotes.append(Euro1x2Quote(
                    company_source_id=company_id, bookmaker_source_name=bookmaker,
                    record_source_id=record_id, ordinal=1, home_odds=home_cur,
                    draw_odds=draw_cur, away_odds=away_cur, market_time_source_raw=market_time,
                    home_kelly=None, draw_kelly=None, away_kelly=None,
                ))
        return tuple(quotes)

    companies: dict[str, tuple[str, str]] = {}
    records: dict[str, tuple[str, str]] = {}
    for item in game_items:
        fields = item.split("|")
        if len(fields) >= 3 and fields[0] and fields[1]:
            companies[fields[1]] = (fields[0], fields[2])
    for item in _array_items(text, "gameDetail"):
        if "^" not in item:
            continue
        record_id, detail = item.split("^", 1)
        if record_id in companies:
            records[record_id] = (detail, record_id)
    for detail, record_id in records.values():
        company_id, bookmaker = companies[record_id]
        for ordinal, item in enumerate(part for part in detail.split(";") if part):
            fields = item.split("|")
            if len(fields) < 3:
                continue
            quotes.append(Euro1x2Quote(
                company_source_id=company_id, bookmaker_source_name=bookmaker, record_source_id=record_id,
                ordinal=ordinal, home_odds=_positive_float(fields[0]), draw_odds=_positive_float(fields[1]),
                away_odds=_positive_float(fields[2]), market_time_source_raw=fields[3] if len(fields) > 3 else None,
                home_kelly=_positive_float(fields[4]) if len(fields) > 4 else None,
                draw_kelly=_positive_float(fields[5]) if len(fields) > 5 else None,
                away_kelly=_positive_float(fields[6]) if len(fields) > 6 else None,
            ))
    return tuple(quotes)


def parse_schedule_ids(payload: bytes) -> Roster:
    """Parse the exact Titan-owned current-football roster variable.

    The response is intentionally not treated as a stable canonical identity;
    it is an observed roster version that must be captured with its raw receipt.
    """
    text = payload.decode("utf-8", errors="strict")
    match = _SCHEDULE_RE.search(text)
    if match is None:
        raise TitanDiscoveryError("Titan soccer_scheduleid variable is absent")
    fixture_ids = tuple(part for part in match.group(1).split(",") if part)
    if not fixture_ids:
        raise TitanDiscoveryError("Titan soccer schedule is empty")
    if len(fixture_ids) != len(set(fixture_ids)):
        raise TitanDiscoveryError("Titan soccer schedule contains duplicate fixture ids")
    if any(not item.isdecimal() or int(item) <= 0 for item in fixture_ids):
        raise TitanDiscoveryError("Titan soccer schedule contains an invalid fixture id")
    return Roster(fixture_ids)


def euro_1x2_url(fixture_id: str) -> str:
    if not fixture_id.isdecimal() or int(fixture_id) <= 0:
        raise TitanDiscoveryError("fixture id must be a positive decimal string")
    return EURO_1X2_URL.format(fixture_id=fixture_id)
