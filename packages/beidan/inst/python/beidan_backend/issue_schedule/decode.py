"""Byte -> text decoding that trusts the source's own charset declaration.

The two frozen 26098 pages disagree: trade.500.com serves ``gb2312`` (really
GBK/GB18030 — it carries characters outside the GB2312 subset), while
cp.nowscore.com serves ``utf-8``.  Decoding everything as gb18030 (what the old
scripts did) silently mangles the nowscore page; decoding everything as utf-8
raises on the 500 page.

So we read the declared charset from the response headers or the ``<meta>`` tag
and decode with exactly that. We never silently fall back to a different codec:
a page whose bytes do not decode with its own declared charset is a source
change that a human must inspect, not something to paper over.
"""

from __future__ import annotations

import codecs
import re
from email.message import Message

#: Charset aliases whose real coverage is wider than the label suggests. A page
#: labelled gb2312 that contains GBK-only characters is normal on Chinese sites,
#: so gb2312 is widened to gb18030. Every other label is used verbatim.
_CHARSET_WIDENING = {"gb2312": "gb18030", "gb-2312": "gb18030", "euc-cn": "gb18030"}

_META_CHARSET_RE = re.compile(
    rb"""<meta[^>]+charset\s*=\s*["']?\s*([A-Za-z0-9_\-]+)""", re.I
)
_META_HTTP_EQUIV_RE = re.compile(
    rb"""<meta[^>]+http-equiv\s*=\s*["']?content-type["']?[^>]+content\s*=\s*["'][^"']*charset=([A-Za-z0-9_\-]+)""",
    re.I,
)


class DecodeError(ValueError):
    """The response could not be decoded with its own declared charset."""


def declared_charset(body: bytes, content_type: str | None = None) -> str:
    """Return the charset the source declares, normalised to a codec name.

    Preference order is HTTP header, then ``<meta charset>``, then
    ``<meta http-equiv=Content-Type>`` — the same order a browser uses, so the
    parser agrees with what a human sees on the page.

    @param body Raw response bytes.
    @param content_type Optional ``Content-Type`` header value.
    @return A Python codec name (e.g. ``"gb18030"``, ``"utf-8"``).
    @raises DecodeError when no charset is declared at all.
    """
    if content_type:
        header = Message()
        header["Content-Type"] = content_type
        charset = header.get_content_charset()
        if charset:
            return _normalise(charset)
    head = body[:4096]
    match = _META_CHARSET_RE.search(head) or _META_HTTP_EQUIV_RE.search(head)
    if match:
        return _normalise(match.group(1).decode("ascii", errors="ignore"))
    raise DecodeError(
        "response declares no charset in Content-Type or <meta>; refusing to guess "
        "because an encoding guess silently corrupts Chinese team names"
    )


def decode_response(body: bytes, content_type: str | None = None) -> str:
    """Decode bytes using the declared charset.

    @param body Raw response bytes.
    @param content_type Optional ``Content-Type`` header value.
    @return The decoded page text.
    @raises DecodeError when the charset is undeclared, unknown, or the bytes do
        not decode with it.
    """
    charset = declared_charset(body, content_type)
    try:
        codec = codecs.lookup(charset)
    except LookupError as error:
        raise DecodeError(f"declared charset {charset!r} is not a known codec") from error
    try:
        return body.decode(codec.name)
    except UnicodeDecodeError as error:
        raise DecodeError(
            f"body does not decode as its declared charset {charset!r}: {error}"
        ) from error


def _normalise(label: str) -> str:
    lowered = label.strip().lower()
    return _CHARSET_WIDENING.get(lowered, lowered)
